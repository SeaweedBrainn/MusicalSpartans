package com.musicalspartans.coach.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.musicalspartans.coach.analytics.Analyzer
import com.musicalspartans.coach.model.PostGameAnalysis
import com.musicalspartans.coach.model.Run
import com.musicalspartans.coach.model.difficultyName
import com.musicalspartans.coach.model.formatTime
import com.musicalspartans.coach.ui.theme.Muted
import com.musicalspartans.coach.ui.theme.Orange
import com.musicalspartans.coach.ui.theme.OrangeSoft
import com.musicalspartans.coach.ui.theme.PrimaryButton
import com.musicalspartans.coach.ui.theme.SecondaryButton
import com.musicalspartans.coach.ui.theme.SoftCard

@Composable
fun ResultsScreen(
    run: Run,
    analysis: PostGameAnalysis,
    source: String,
    onSpeak: () -> Unit,
    onOpenReplay: () -> Unit,
    onDone: () -> Unit,
) {
    val summary = run.summary

    Column(
        Modifier.fillMaxSize().padding(20.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(source, Modifier.weight(1f), style = MaterialTheme.typography.bodySmall)
            TextButton(onClick = onDone) { Text("Done with song", color = Orange) }
        }

        SoftCard {
            Text("Song ${summary.songId}  ·  ${difficultyName(summary.difficulty)}", color = Muted)
            Text("%,d".format(analysis.score), style = MaterialTheme.typography.displayMedium)
            Text("Grade ${Analyzer.grade(analysis.accuracy)}   ·   %.1f%% accuracy".format(analysis.accuracy * 100))
            Text("${summary.totalNotes} notes   ·   %.1f notes/sec   ·   ${summary.bpm} BPM".format(Analyzer.notesPerSecond(summary)), color = Muted)
            analysis.meanOffsetMs?.let { Text("Average timing  %+.0f ms".format(it), color = Orange) }
        }

        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            PrimaryButton("Read aloud", onSpeak, modifier = Modifier.weight(1f))
            SecondaryButton("Watch replay", onOpenReplay, modifier = Modifier.weight(1f))
        }

        Text("By section", style = MaterialTheme.typography.titleMedium)
        analysis.sections.forEach { s ->
            val timing = s.meanOffsetMS?.let { "   %+.0f ms".format(it) } ?: ""
            Text("${formatTime(s.startMs)} – ${formatTime(s.endMs)}   %.0f%%".format(s.accuracy * 100) + timing)
            LinearProgressIndicator(
                progress = { s.accuracy.toFloat() },
                modifier = Modifier.fillMaxWidth(),
                color = Orange,
                trackColor = OrangeSoft,
            )
        }

        Text("Coaching", style = MaterialTheme.typography.titleMedium)
        if (analysis.tips.isEmpty()) {
            SoftCard { Text("No problem spots found. Nice run!") }
        }
        analysis.tips.forEach { tip ->
            SoftCard {
                Text(formatTime(tip.timeMs), color = Orange, style = MaterialTheme.typography.labelLarge)
                Text(tip.text)
            }
        }
    }
}
