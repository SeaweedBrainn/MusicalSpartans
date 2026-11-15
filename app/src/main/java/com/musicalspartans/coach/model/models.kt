package com.musicalspartans.coach.model

//Song summary file (one line, no header)
/**
 * difficulty - 1 Beginner, 2 Easy, 3 Medium, 4 Hard
 * gameTimeMs - song length in milliseconds
 * score - score the game calculated (0 - 1,000,000)
 * averageLatencyMs - average of InputTime - NoteTime (negative = early)
 */
data class RunSummary(val gameId: Int, val songId: Int, val difficulty: Int, val gameTimeMs: Long,
                      val bpm: Int, val totalNotes: Int, val score: Int, val averageLatencyMs: Double)

//One row of the timeline file (one row every sample_interval_sec)
/**
 * timeSec - seconds into the song
 * accuracy - 0.0 to 1.0, null if no notes in this sample
 * avgLatencyMs - average InputTime - NoteTime (negative = early), null if no notes
 * bpm - tempo at this time
 * nps - number of notes in this sample
 * latencySpreadMs - how much hits varied, null if fewer than 2 notes
 */
data class TimelineSample(val timeSec: Double, val accuracy: Double?, val avgLatencyMs: Double?,
                          val bpm: Int, val nps: Int, val latencySpreadMs: Double?)

//For one song
/**
 * chartId - which chart of the song was played
 * samples - every row of the timeline file
 * videoURI - identifier of video
 * videoOffsetMs - time offset to sync video w/ gameplay
 */
data class Run(val summary: RunSummary, val chartId: Int, val samples: List<TimelineSample>,
               val videoURI: String, val videoOffsetMs: Long)

//For specific section of song
/**
 * accuracy - 0.0 to 1.0
 * meanOffsetMS - avg timing offset (negative = early)
 * spreadMs - avg latency spread, null if not enough notes
 */
data class SectionStat(val startMs: Long, val endMs: Long, val accuracy: Double,
                       val meanOffsetMS: Double?, val spreadMs: Double?)

//For coaching the player and giving tips
/**
 * timeMs - time frame for where AI gives tip
 * text - advice to output
 */
data class Guide(val timeMs: Long, val text: String, val spansSong: Boolean = false)

//Analyzing gameplay
/**
 * score - final score from game
 * accuracy - overall accuracy, 0.0 to 1.0
 * meanOffsetMs - average timing offset across the song
 * sections - performance stats for each part of the song
 * tips - advice (rule based for now, AI later)
 */
data class PostGameAnalysis(val score: Int, val accuracy: Double, val meanOffsetMs: Double?,
                            val sections: List<SectionStat>, val tips: List<Guide>)

//function to make milliseconds to m:ss format
fun formatTime(ms: Long): String = "%d:%02d".format(ms / 60_000, (ms / 1000) % 60)

//function for difficulty
fun difficultyName(level: Int): String = when (level) {
    1 -> "Beginner"
    2 -> "Easy"
    3 -> "Medium"
    4 -> "Hard"
    else -> "Unknown"
}