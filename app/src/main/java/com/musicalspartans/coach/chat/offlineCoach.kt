package com.musicalspartans.coach.chat

import com.musicalspartans.coach.analytics.SessionReporter
import com.musicalspartans.coach.model.SongSummary
import com.musicalspartans.coach.model.songLabel
import kotlin.math.abs
import kotlin.math.roundToInt

//Rule-based coach: recognizes common questions and answers them from the saved analytics
class OfflineCoach : CoachChat {
    override val label = "Offline coach (no AI key set)"

    override suspend fun reply(history: List<ChatMessage>, context: CoachContext): String {
        val question = history.lastOrNull { it.fromUser }?.text?.lowercase().orEmpty()
        val words = question.split(Regex("[^a-z]+")).filter { it.isNotBlank() }
        fun asks(vararg starts: String) = starts.any { s -> words.any { it.startsWith(s) } }

        val songs = context.allSongs
        return when {
            question.trim() == "help" || "what can you" in question -> HELP
            songs.isEmpty() -> "I don't have any data yet. Import a song on the Song tab, then ask me again."
            words.any { it in GREETINGS } && words.size <= 3 -> "Hey! Ask me about your timing, your best or hardest song, or whether you're improving."
            asks("timing", "late", "early", "latency", "offset", "rush", "drag", "slow", "fast") -> timing(songs)
            asks("best", "top", "highest") -> best(songs)
            asks("worst", "hardest", "struggl", "weak", "bad", "lowest") -> hardest(songs)
            asks("progress", "improv", "trend", "better", "getting") -> progress(context)
            asks("practic", "tip", "advice", "focus", "work") -> advice(songs)
            asks("count", "total", "many") -> counts(context)
            asks("last", "latest", "recent", "session", "report", "summary") -> latest(context)
            else -> "I'm the offline coach, so I can only answer questions about your stats. " +
                    "Try: \"How's my timing?\", \"What should I practice?\" or \"Am I improving?\" " +
                    "For open conversation, add a free Gemini key (see the Settings tab)."
        }
    }

    private fun timing(songs: List<SongSummary>): String {
        val offsets = songs.mapNotNull { it.meanOffsetMs }
        if (offsets.isEmpty()) return "I don't have timing data for your songs yet."
        val average = offsets.average()
        val latest = songs.last { it.meanOffsetMs != null }
        val advice = when {
            average > 20 -> " That's a consistent lag, so try moving the game's audio offset about ${average.roundToInt()} ms earlier, or aim slightly ahead of the beat."
            average < -20 -> " You're rushing, so try listening for the beat instead of reacting to the notes, or move the audio offset about ${(-average).roundToInt()} ms later."
            else -> " Nice, that's well centered."
        }
        return "Across ${offsets.size} songs, ${SessionReporter.timingSentence(average)}. " +
                "Most recently, ${songLabel(latest)} was %+.0f ms.".format(latest.meanOffsetMs) + advice
    }

    private fun best(songs: List<SongSummary>): String {
        val s = songs.maxBy { it.accuracy }
        return "Your best was ${songLabel(s)} with ${s.score} points (${pct(s.accuracy)}, grade ${s.grade})."
    }

    private fun hardest(songs: List<SongSummary>): String {
        val s = songs.minBy { it.accuracy }
        val section = s.weakestSectionStartMs?.let { " The roughest part started around ${it / 1000} seconds in." } ?: ""
        return "Your hardest was ${songLabel(s)} at ${pct(s.accuracy)} (grade ${s.grade}).$section"
    }

    private fun progress(context: CoachContext): String {
        val reports = context.reports
        if (reports.size >= 2) {
            val oldest = reports.last()
            val newest = reports.first()
            val change = (newest.averageAccuracy - oldest.averageAccuracy) * 100
            val trend = when {
                change > 2 -> "you're improving: up %.1f points".format(change)
                change < -2 -> "you're down %.1f points, so maybe take a break or drop the difficulty".format(-change)
                else -> "you're holding steady"
            }
            return "Comparing your first and latest of ${reports.size} sessions, $trend " +
                    "(${pct(oldest.averageAccuracy)} → ${pct(newest.averageAccuracy)})."
        }
        val songs = context.allSongs
        if (songs.size < 2) return "Play a few more songs and I can tell you if you're improving."
        val change = (songs.last().accuracy - songs.first().accuracy) * 100
        return "From your first song to your latest, accuracy went from ${pct(songs.first().accuracy)} to ${pct(songs.last().accuracy)} " +
                "(%+.1f points). Save a few session reports and I can track longer-term progress.".format(change)
    }

    private fun advice(songs: List<SongSummary>): String {
        val hardest = songs.minBy { it.accuracy }
        val offsets = songs.mapNotNull { it.meanOffsetMs }
        val timing = offsets.takeIf { it.isNotEmpty() }?.average()?.let {
            if (abs(it) > 20) " Overall, ${SessionReporter.timingSentence(it)}, so fixing that will raise every score." else ""
        } ?: ""

        if (hardest.accuracy >= 0.95) {
            return "Your accuracy is excellent: even your lowest song was ${pct(hardest.accuracy)}.$timing " +
                    "To keep improving, move up a difficulty level."
        }
        val tips = hardest.tips.take(2).joinToString("; ") { it.trimEnd('.') }
        val tipText = if (tips.isEmpty()) "" else " Tips from that song: $tips."
        return "Focus on ${songLabel(hardest)}, your lowest at ${pct(hardest.accuracy)}.$tipText$timing " +
                "Replay the hard part at half speed on the Song tab, then build back up."
    }

    private fun counts(context: CoachContext): String =
        "You have ${context.reports.size} saved session reports covering ${context.reports.sumOf { it.songs.size }} songs, " +
                "plus ${context.currentSession.size} songs in your current session."

    private fun latest(context: CoachContext): String =
        context.reports.firstOrNull()?.let { SessionReporter.asText(it) }
            ?: "No saved reports yet. Your current session has ${context.currentSession.size} songs, so generate a report on the Song tab."

    private fun pct(accuracy: Double) = "%.1f%%".format(accuracy * 100)

    private companion object {
        val GREETINGS = setOf("hi", "hello", "hey", "yo", "sup")
        const val HELP = "I can answer questions about your saved analytics. Try:\n" +
                "• How's my timing?\n• What was my best song?\n• What's my hardest song?\n" +
                "• Am I improving?\n• What should I practice?\n• Summarize my last session\n• How many sessions do I have?"
    }
}
