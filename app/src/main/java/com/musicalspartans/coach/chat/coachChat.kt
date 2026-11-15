package com.musicalspartans.coach.chat

import com.musicalspartans.coach.analytics.SessionReporter
import com.musicalspartans.coach.model.SessionReport
import com.musicalspartans.coach.model.SongSummary

data class ChatMessage(val fromUser: Boolean, val text: String)

//What the coach knows about the player
/**
 * reports - saved session reports, newest first
 * currentSession - songs played since the last session report
 */
data class CoachContext(val reports: List<SessionReport>, val currentSession: List<SongSummary>) {
    val allSongs: List<SongSummary> get() = reports.flatMap { it.songs } + currentSession

    //Plain-text version of the player's data for an AI prompt
    fun asText(maxReports: Int = 10): String = buildString {
        if (reports.isEmpty() && currentSession.isEmpty()) {
            append("The player has no saved data yet.")
            return@buildString
        }
        reports.take(maxReports).forEach { appendLine(SessionReporter.asText(it)); appendLine() }
        if (currentSession.isNotEmpty()) {
            appendLine("Current session so far (no report generated yet):")
            appendLine(SessionReporter.asText(SessionReporter.build(currentSession, currentSession.last().playedAt)))
        }
    }.trim()
}

//The chatbot. OfflineCoach works with no internet or API key; GeminiCoach is a real AI.
interface CoachChat {
    val label: String
    suspend fun reply(history: List<ChatMessage>, context: CoachContext): String
}
