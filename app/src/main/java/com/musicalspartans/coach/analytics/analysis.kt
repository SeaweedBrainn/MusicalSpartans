package com.musicalspartans.coach.analytics

import com.musicalspartans.coach.model.Guide
import com.musicalspartans.coach.model.PostGameAnalysis
import com.musicalspartans.coach.model.Run
import com.musicalspartans.coach.model.RunSummary
import com.musicalspartans.coach.model.SectionStat
import com.musicalspartans.coach.model.TimelineSample
import kotlin.math.abs
import kotlin.math.roundToInt

object Analyzer {
    private const val MAX_SCORE = 1_000_000.0
    private const val SECTION_SEC = 5.0     //group samples into 5 second sections
    private const val TIMING_MS = 20.0      //early/late more than this is worth a tip
    private const val SPREAD_MS = 15.0      //spread more than this is "inconsistent"

    fun analyze(run: Run): PostGameAnalysis {
        //only seconds where notes were played
        val played = run.samples.filter { it.nps > 0 && it.accuracy != null }

        val sections = played.groupBy { (it.timeSec / SECTION_SEC).toInt() }
            .toSortedMap()
            .map { (bucket, samples) -> sectionStat(bucket, samples) }

        //summary-only imports have no timeline, so fall back to the game's own average
        val songOffset = weighted(played) { it.avgLatencyMs } ?: run.summary.averageLatencyMs

        return PostGameAnalysis(
            score = run.summary.score,
            accuracy = run.summary.score / MAX_SCORE,
            meanOffsetMs = songOffset,
            sections = sections,
            tips = tipsFor(songOffset, sections),
        )
    }

    //Letter grade from the design doc (accuracy is 0.0 - 1.0)
    fun grade(accuracy: Double): String = when {
        accuracy >= 1.0 -> "Perfect"
        accuracy >= 0.95 -> "S"
        accuracy >= 0.90 -> "A"
        accuracy >= 0.80 -> "B"
        accuracy >= 0.70 -> "C"
        else -> "Fail"
    }

    fun notesPerSecond(summary: RunSummary): Double =
        if (summary.gameTimeMs == 0L) 0.0 else summary.totalNotes / (summary.gameTimeMs / 1000.0)

    fun spokenSummary(a: PostGameAnalysis): String = buildString {
        append("You scored ${a.score}, grade ${grade(a.accuracy)}. ")
        a.tips.firstOrNull()?.let { append(it.text) }
    }

    private fun sectionStat(bucket: Int, samples: List<TimelineSample>): SectionStat {
        val startMs = (bucket * SECTION_SEC * 1000).toLong()
        return SectionStat(
            startMs = startMs,
            endMs = startMs + (SECTION_SEC * 1000).toLong(),
            accuracy = weighted(samples) { it.accuracy } ?: 0.0,
            meanOffsetMS = weighted(samples) { it.avgLatencyMs },
            spreadMs = samples.mapNotNull { it.latencySpreadMs }.takeIf { it.isNotEmpty() }?.average(),
        )
    }

    //Average where a second with 4 notes counts 4 times as much as a second with 1 note
    private fun weighted(samples: List<TimelineSample>, value: (TimelineSample) -> Double?): Double? {
        val pairs = samples.mapNotNull { s -> value(s)?.let { it to s.nps } }
        val totalNotes = pairs.sumOf { it.second }
        return if (totalNotes == 0) null else pairs.sumOf { it.first * it.second } / totalNotes
    }

    //Placeholder tips until the AI is ready
    private fun tipsFor(songOffset: Double?, sections: List<SectionStat>): List<Guide> {
        val tips = mutableListOf<Guide>()

        //whole song bias: always late or always early
        if (songOffset != null && abs(songOffset) > TIMING_MS) {
            val direction = if (songOffset > 0) "late" else "early"
            tips += Guide(0, "You hit ${abs(songOffset).roundToInt()} ms $direction on average across the whole song. " +
                    "If this happens every song, adjust the game's audio offset.", spansSong = true)
        }

        sections.forEach { s ->
            sectionProblem(s, songOffset ?: 0.0)?.let { tips += Guide(s.startMs, it) }
        }
        return tips
    }

    //Compares a section to the rest of the song so a whole-song bias isn't repeated every section
    private fun sectionProblem(s: SectionStat, songOffset: Double): String? {
        val drift = s.meanOffsetMS?.minus(songOffset)
        val spread = s.spreadMs
        return when {
            s.accuracy < 0.9 -> "accuracy dropped to ${(s.accuracy * 100).roundToInt()}%."
            drift != null && drift < -TIMING_MS -> "you sped up, hitting ${(-drift).roundToInt()} ms earlier than the rest of the song."
            drift != null && drift > TIMING_MS -> "you fell behind, hitting ${drift.roundToInt()} ms later than the rest of the song."
            spread != null && spread > SPREAD_MS -> "your timing was inconsistent (spread of ${spread.roundToInt()} ms)."
            else -> null
        }
    }
}