package com.musicalspartans.coach

import com.musicalspartans.coach.analytics.Analyzer
import com.musicalspartans.coach.data.CSVParser
import com.musicalspartans.coach.model.Run
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class GameCsvTest {
    private val summaryCsv = "01,010,2,14000,120,25,1000000,26"

    private val timelineCsv = """
        game_id,1
        song_id,10
        chart_id,1
        bpm,120
        sample_interval_sec,1
        game_time,percent_accuracy,avg_latency,bpm,nps,latency_spread
        0,,,120,0,
        1,,,120,0,
        2,100,40,120,2,3
        3,100,25,120,2,3
        4,100,8,120,2,1
        5,100,32,120,1,
        6,100,27,120,3,5
        7,100,22,120,2,7
        8,100,24,120,2,3
        9,100,35,120,1,
        10,100,28,120,4,5
        11,100,31,120,4,8
        12,100,16,120,2,6
        13,,,120,0,
    """.trimIndent()

    @Test
    fun parsesGameFiles() {
        val summary = CSVParser.parseSummary(summaryCsv)
        val timeline = CSVParser.parseTimeline(timelineCsv)

        assertEquals(10, summary.songId)
        assertEquals(1, timeline.chartId)
        assertEquals(14, timeline.samples.size)
        //notes per second should add up to the summary's note count
        assertEquals(summary.totalNotes, timeline.samples.sumOf { it.nps })
    }

    @Test
    fun lateButAccurateRunGetsLatencyTip() {
        val summary = CSVParser.parseSummary(summaryCsv)
        val timeline = CSVParser.parseTimeline(timelineCsv)
        val result = Analyzer.analyze(Run(summary, timeline.chartId, timeline.samples, "", 0))

        assertEquals("Perfect", Analyzer.grade(result.accuracy))
        assertEquals(26.16, result.meanOffsetMs!!, 0.01)
        assertTrue(result.tips.first().text.contains("late"))
    }
}
