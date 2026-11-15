package com.musicalspartans.coach.data

import com.musicalspartans.coach.model.SessionReport
import com.musicalspartans.coach.model.SongSummary
import kotlinx.serialization.json.Json
import java.io.File
import java.time.Instant
import java.time.ZoneId
import java.time.ZoneOffset

//Phone storage for analytics. Pass context.filesDir in the app (private to the app, survives restarts).
//  current_session.txt  - one song summary per line until a session report is generated
//  reports/<id>.json    - saved session reports
//Call from a background thread (Dispatchers.IO).
class SessionStore(dir: File) {
    private val json = Json { ignoreUnknownKeys = true }
    private val sessionFile = File(dir, "current_session.txt")
    private val reportsDir = File(dir, "reports")

    fun addSong(song: SongSummary) {
        sessionFile.parentFile?.mkdirs()
        sessionFile.appendText(json.encodeToString(song) + "\n")
    }

    fun currentSession(): List<SongSummary> =
        if (!sessionFile.exists()) emptyList()
        else sessionFile.readLines().filter { it.isNotBlank() }.map { json.decodeFromString<SongSummary>(it) }

    fun clearSession() {
        sessionFile.delete()
    }

    fun saveReport(report: SessionReport) {
        reportsDir.mkdirs()
        File(reportsDir, "${report.id}.json").writeText(json.encodeToString(report))
    }

    //Newest first
    fun reports(): List<SessionReport> =
        reportFiles().map { json.decodeFromString<SessionReport>(it.readText()) }
            .sortedByDescending { it.createdAt }

    //Deletes reports created between fromMs and toMs (inclusive). Returns how many were deleted.
    fun deleteReports(fromMs: Long, toMs: Long): Int =
        reportFiles().count { file ->
            val report = json.decodeFromString<SessionReport>(file.readText())
            report.createdAt in fromMs..toMs && file.delete()
        }

    fun deleteAllReports(): Int = reportFiles().count { it.delete() }

    private fun reportFiles(): List<File> =
        reportsDir.listFiles { f -> f.extension == "json" }?.toList() ?: emptyList()
}

//Date pickers return UTC midnight; convert the picked days to the phone's local start/end of day
fun localDayBounds(startUtcMs: Long, endUtcMs: Long, zone: ZoneId = ZoneId.systemDefault()): Pair<Long, Long> {
    val startDay = Instant.ofEpochMilli(startUtcMs).atZone(ZoneOffset.UTC).toLocalDate()
    val endDay = Instant.ofEpochMilli(endUtcMs).atZone(ZoneOffset.UTC).toLocalDate()
    val from = startDay.atStartOfDay(zone).toInstant().toEpochMilli()
    val to = endDay.plusDays(1).atStartOfDay(zone).toInstant().toEpochMilli() - 1
    return from to to
}
