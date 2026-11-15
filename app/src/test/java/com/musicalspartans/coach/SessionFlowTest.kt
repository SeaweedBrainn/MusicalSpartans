package com.musicalspartans.coach

import com.musicalspartans.coach.analytics.Analyzer
import com.musicalspartans.coach.analytics.SessionReporter
import com.musicalspartans.coach.chat.ChatMessage
import com.musicalspartans.coach.chat.CoachContext
import com.musicalspartans.coach.chat.GeminiCoach
import com.musicalspartans.coach.chat.OfflineCoach
import com.musicalspartans.coach.data.RunImporter
import com.musicalspartans.coach.data.SessionStore
import com.musicalspartans.coach.data.localDayBounds
import com.musicalspartans.coach.model.SongSummary
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZoneOffset

class SessionFlowTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private val assets = File("src/main/assets")
    private val summaryCsv get() = File(assets, "song10-chart1-summary.csv").readText()
    private val timelineCsv get() = File(assets, "song10-chart1.csv").readText()

    private fun song(accuracy: Double, offset: Double?, playedAt: Long) = SongSummary(
        songId = 10, chartId = 1, difficulty = 2, playedAt = playedAt, score = (accuracy * 1_000_000).toInt(),
        grade = Analyzer.grade(accuracy), accuracy = accuracy, totalNotes = 25, gameTimeMs = 14_000, bpm = 120,
        meanOffsetMs = offset, weakestSectionStartMs = 5_000, weakestSectionAccuracy = accuracy, tips = emptyList(),
    )

    @Test
    fun importAcceptsFilesInAnyOrderAndSummaryAlone() {
        val both = RunImporter.fromTexts(listOf(timelineCsv, summaryCsv))
        assertEquals(14, both.samples.size)

        val summaryOnly = RunImporter.fromTexts(listOf(summaryCsv))
        assertTrue(summaryOnly.samples.isEmpty())
        //no timeline -> analyzer falls back to the game's own average latency
        assertEquals(26.0, Analyzer.analyze(summaryOnly).meanOffsetMs!!, 0.001)
    }

    @Test(expected = IllegalArgumentException::class)
    fun importRejectsTwoSummaries() {
        RunImporter.fromTexts(listOf(summaryCsv, summaryCsv))
    }

    @Test
    fun songsBecomeSavedReportAndSessionResets() {
        val store = SessionStore(tmp.root)
        val run = RunImporter.fromTexts(listOf(summaryCsv, timelineCsv))
        store.addSong(SessionReporter.songSummary(run, Analyzer.analyze(run), playedAt = 1_000))
        store.addSong(song(0.85, 10.0, playedAt = 2_000))
        assertEquals(2, store.currentSession().size)

        val report = SessionReporter.build(store.currentSession(), createdAt = 3_000)
        store.saveReport(report)
        store.clearSession()

        assertTrue(store.currentSession().isEmpty())
        val saved = SessionStore(tmp.root).reports().single()  //new instance = survives app restart
        assertEquals(report, saved)
        assertTrue(saved.highlights.any { "dropped" in it })  //100% -> 85%
    }

    @Test
    fun deleteReportsOnlyInsideRange() {
        val store = SessionStore(tmp.root)
        listOf(1_000L, 5_000L, 9_000L).forEach { store.saveReport(SessionReporter.build(listOf(song(0.9, 0.0, it)), it)) }

        assertEquals(1, store.deleteReports(4_000, 6_000))
        assertEquals(listOf(9_000L, 1_000L), store.reports().map { it.createdAt })
        assertEquals(2, store.deleteAllReports())
    }

    @Test
    fun pickedDaysCoverWholeLocalDays() {
        val zone = ZoneId.of("America/Los_Angeles")
        val pickedUtc = LocalDate.of(2026, 11, 14).atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli()
        val (from, to) = localDayBounds(pickedUtc, pickedUtc, zone)
        //a report at 11:30 PM local time on Nov 14 is inside the range
        val lateEvening = LocalDate.of(2026, 11, 14).atTime(23, 30).atZone(zone).toInstant().toEpochMilli()
        assertTrue(lateEvening in from..to)
        assertEquals(24 * 60 * 60 * 1000L - 1, to - from)
    }

    @Test
    fun offlineCoachAnswersFromSavedData() = runBlocking {
        val coach = OfflineCoach()
        val context = CoachContext(
            reports = listOf(SessionReporter.build(listOf(song(0.95, 30.0, 2)), 3), SessionReporter.build(listOf(song(0.80, 30.0, 0)), 1)),
            currentSession = emptyList(),
        )
        fun ask(q: String) = runBlocking { coach.reply(listOf(ChatMessage(true, q)), context) }

        assertTrue(ask("How's my timing?").contains("late"))
        assertTrue(ask("Am I improving?").contains("improving"))
        assertTrue(ask("what was my best song").contains("95.0%"))
        assertTrue(coach.reply(listOf(ChatMessage(true, "timing?")), CoachContext(emptyList(), emptyList())).contains("don't have any data"))
    }

    @Test
    fun geminiRequestStartsWithUserAndParsesReply() {
        val history = listOf(ChatMessage(false, "Hi! I'm your coach."), ChatMessage(true, "How's my timing?"))
        val contents = GeminiCoach.buildRequest(history, "system")["contents"]!!.jsonArray
        assertEquals(1, contents.size)
        assertEquals("user", contents[0].jsonObject["role"]!!.jsonPrimitive.content)

        val response = """{"candidates":[{"content":{"parts":[{"text":"You're 26 ms late."}],"role":"model"}}]}"""
        assertEquals("You're 26 ms late.", GeminiCoach.parseReply(response))
    }
}
