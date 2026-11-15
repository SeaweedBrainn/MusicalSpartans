package com.musicalspartans.coach.data

import android.content.Context
import com.musicalspartans.coach.model.Run
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

const val SAMPLE_VIDEO_URI = "asset:///sample_gameplay.mp4"
const val SAMPLE_RUN_ID = "song10-chart1"

//Where runs come from. Screens only know about this interface.
//suspend = runs in the background so loading never freezes the screen
interface RunRepository {
    suspend fun loadRun(runId: String): Run
}

//Reads the game's two CSV files bundled in assets/ (sample song for demos)
//runId "song10-chart1" -> song10-chart1-summary.csv + song10-chart1.csv
class FakeRunRepository(private val context: Context) : RunRepository {
    override suspend fun loadRun(runId: String): Run = withContext(Dispatchers.IO) {
        RunImporter.fromTexts(listOf(readAsset("$runId-summary.csv"), readAsset("$runId.csv")))
    }

    private fun readAsset(name: String): String =
        context.assets.open(name).bufferedReader().use { it.readText() }
}

//Builds a Run from the game's files, in any order. The timeline file is optional.
object RunImporter {
    fun fromTexts(texts: List<String>): Run {
        val (timelines, summaries) = texts.partition { CSVParser.isTimeline(it) }
        require(summaries.size == 1) { "Pick exactly one summary file (the one-line CSV). Got ${summaries.size}." }
        require(timelines.size <= 1) { "Pick at most one timeline file. Got ${timelines.size}." }

        val summary = CSVParser.parseSummary(summaries.single())
        val timeline = timelines.singleOrNull()?.let { CSVParser.parseTimeline(it) }
        require(timeline == null || timeline.songId == summary.songId) {
            "These files are from different songs (summary: song ${summary.songId}, timeline: song ${timeline?.songId})."
        }

        return Run(
            summary = summary,
            chartId = timeline?.chartId ?: 0,
            samples = timeline?.samples ?: emptyList(),
            videoURI = SAMPLE_VIDEO_URI,
            videoOffsetMs = 0,
        )
    }
}
