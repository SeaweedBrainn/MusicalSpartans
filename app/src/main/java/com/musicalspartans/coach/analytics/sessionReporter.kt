package com.musicalspartans.coach.analytics

import com.musicalspartans.coach.model.PostGameAnalysis
import com.musicalspartans.coach.model.Run
import com.musicalspartans.coach.model.SessionReport
import com.musicalspartans.coach.model.SongSummary
import com.musicalspartans.coach.model.formatDateTime
import com.musicalspartans.coach.model.formatTime
import com.musicalspartans.coach.model.songLabel
import kotlin.math.abs
import kotlin.math.roundToInt

object SessionReporter {
    private const val TIMING_MS = 20.0
    private const val TREND = 0.02  //accuracy change worth mentioning (2 points)

    //Per-song summary: everything a session report or the chatbot needs, without the per-second data
    fun songSummary(run: Run, analysis: PostGameAnalysis, playedAt: Long): SongSummary {
        val weakest = analysis.sections.minByOrNull { it.accuracy }
        return SongSummary(
            songId = run.summary.songId,
            chartId = run.chartId,
            difficulty = run.summary.difficulty,
            playedAt = playedAt,
            score = analysis.score,
            grade = Analyzer.grade(analysis.accuracy),
            accuracy = analysis.accuracy,
            totalNotes = run.summary.totalNotes,
            gameTimeMs = run.summary.gameTimeMs,
            bpm = run.summary.bpm,
            meanOffsetMs = analysis.meanOffsetMs,
            weakestSectionStartMs = weakest?.startMs,
            weakestSectionAccuracy = weakest?.accuracy,
            tips = analysis.tips.map { "${formatTime(it.timeMs)} ${it.text}" },
        )
    }

    fun build(songs: List<SongSummary>, createdAt: Long): SessionReport {
        require(songs.isNotEmpty()) { "Play at least one song before generating a session report." }
        val offsets = songs.mapNotNull { it.meanOffsetMs }
        val averageOffset = offsets.takeIf { it.isNotEmpty() }?.average()
        return SessionReport(
            id = "report-$createdAt",
            createdAt = createdAt,
            songs = songs.sortedBy { it.playedAt },
            averageAccuracy = songs.map { it.accuracy }.average(),
            averageOffsetMs = averageOffset,
            highlights = highlights(songs.sortedBy { it.playedAt }, averageOffset),
        )
    }

    fun timingSentence(offsetMs: Double): String = when {
        offsetMs > TIMING_MS -> "you hit ${offsetMs.roundToInt()} ms late on average"
        offsetMs < -TIMING_MS -> "you hit ${(-offsetMs).roundToInt()} ms early on average"
        else -> "your timing was centered (%+.0f ms on average)".format(offsetMs)
    }

    //Full text version: shown on screen and given to the chatbot as context
    fun asText(r: SessionReport): String = buildString {
        appendLine("Session report from ${formatDateTime(r.createdAt)}")
        appendLine("${r.songs.size} songs, average accuracy ${pct(r.averageAccuracy)}" +
                (r.averageOffsetMs?.let { ", average timing %+.0f ms".format(it) } ?: ""))
        r.highlights.forEach { appendLine("- $it") }
        r.songs.forEachIndexed { i, s ->
            append("${i + 1}. ${songLabel(s)}: score ${s.score}, grade ${s.grade}, accuracy ${pct(s.accuracy)}")
            s.meanOffsetMs?.let { append(", timing %+.0f ms".format(it)) }
            appendLine()
            s.tips.forEach { appendLine("   tip: $it") }
        }
    }.trim()

    fun spoken(r: SessionReport): String =
        "Session report. ${r.songs.size} songs with ${(r.averageAccuracy * 100).roundToInt()} percent average accuracy. " +
                r.highlights.joinToString(" ")

    private fun highlights(songs: List<SongSummary>, averageOffset: Double?): List<String> = buildList {
        val best = songs.maxBy { it.accuracy }
        add("Best song: ${songLabel(best)} at ${pct(best.accuracy)} (${best.grade}).")

        if (songs.size > 1) {
            val hardest = songs.minBy { it.accuracy }
            if (hardest != best) add("Hardest song: ${songLabel(hardest)} at ${pct(hardest.accuracy)} (${hardest.grade}).")

            val change = songs.last().accuracy - songs.first().accuracy
            add(when {
                change > TREND -> "You improved by ${points(change)} points from your first song to your last."
                change < -TREND -> "Accuracy dropped ${points(-change)} points by the end. You may be getting tired, so take a break."
                else -> "Your accuracy stayed steady across the session."
            })
        }

        if (averageOffset != null) {
            val sentence = timingSentence(averageOffset).replaceFirstChar { it.uppercase() } + "."
            add(if (abs(averageOffset) > TIMING_MS) "$sentence Try adjusting the game's audio offset or aim slightly ${if (averageOffset > 0) "earlier" else "later"}." else sentence)
        }
    }

    private fun pct(accuracy: Double) = "%.1f%%".format(accuracy * 100)

    private fun points(change: Double) = "%.1f".format(change * 100)
}
