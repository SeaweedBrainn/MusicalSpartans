package com.musicalspartans.coach.data

import com.musicalspartans.coach.model.RunSummary
import com.musicalspartans.coach.model.TimelineSample

//Metadata + rows from the timeline file
data class Timeline(val gameId: Int, val songId: Int, val chartId: Int,
                    val sampleIntervalSec: Double, val samples: List<TimelineSample>)

object CSVParser {

    //One line, no header:
    //game_id,song_id,difficulty,game_time_ms,bpm,total_notes,score,avg_latency_ms
    fun parseSummary(text: String): RunSummary {
        val c = text.trim().split(",").map { it.trim() }
        require(c.size >= 8) { "Summary needs 8 values, got ${c.size}" }
        return RunSummary(
            gameId = c[0].toInt(),
            songId = c[1].toInt(),
            difficulty = c[2].toInt(),
            gameTimeMs = c[3].toLong(),
            bpm = c[4].toInt(),
            totalNotes = c[5].toInt(),
            score = c[6].toInt(),
            averageLatencyMs = c[7].toDouble(),
        )
    }

    fun isTimeline(text: String): Boolean =
        text.lineSequence().any { it.trim().startsWith("game_time,") }

    //"key,value" lines, then a header row starting with game_time, then one row per sample
    fun parseTimeline(text: String): Timeline {
        val lines = text.replace("\r", "").lines().filter { it.isNotBlank() }

        val headerIndex = lines.indexOfFirst { it.trim().startsWith("game_time,") }
        require(headerIndex >= 0) { "Timeline has no game_time header row" }

        //everything above the header: game_id,1  song_id,10 ...
        val meta = lines.take(headerIndex).associate { line ->
            val (key, value) = line.split(",", limit = 2).map { it.trim() }
            key.lowercase() to value
        }

        val header = lines[headerIndex].split(",").map { it.trim().lowercase() }

        //match each value with its column name, empty values become null
        val samples = lines.drop(headerIndex + 1).map { line ->
            val r = header.zip(line.split(",").map { it.trim() }).toMap()
            TimelineSample(
                timeSec = r.getValue("game_time").toDouble(),
                accuracy = r["percent_accuracy"]?.toDoubleOrNull()?.div(100),
                avgLatencyMs = r["avg_latency"]?.toDoubleOrNull(),
                bpm = r["bpm"]?.toIntOrNull() ?: 0,
                nps = r["nps"]?.toIntOrNull() ?: 0,
                latencySpreadMs = r["latency_spread"]?.toDoubleOrNull(),
            )
        }

        return Timeline(
            gameId = meta.getValue("game_id").toInt(),
            songId = meta.getValue("song_id").toInt(),
            chartId = meta.getValue("chart_id").toInt(),
            sampleIntervalSec = meta["sample_interval_sec"]?.toDoubleOrNull() ?: 1.0,
            samples = samples,
        )
    }
}