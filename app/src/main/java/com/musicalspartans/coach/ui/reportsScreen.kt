package com.musicalspartans.coach.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.musicalspartans.coach.analytics.SessionReporter
import com.musicalspartans.coach.model.SessionReport
import com.musicalspartans.coach.model.formatDateTime
import com.musicalspartans.coach.model.songLabel
import com.musicalspartans.coach.ui.theme.Muted
import com.musicalspartans.coach.ui.theme.Orange
import com.musicalspartans.coach.ui.theme.PrimaryButton
import com.musicalspartans.coach.ui.theme.SoftCard

@Composable
fun ReportsScreen(reports: List<SessionReport>, onSpeak: (String) -> Unit) {
    var openId by rememberSaveable { mutableStateOf<String?>(null) }
    val open = reports.find { it.id == openId }

    if (open != null) {
        BackHandler { openId = null }
        ReportDetailScreen(open, onBack = { openId = null }, onSpeak = onSpeak)
        return
    }

    if (reports.isEmpty()) {
        Text(
            "No session reports yet. Import songs on the Song tab, then tap \"Generate session report\".",
            Modifier.padding(20.dp),
            color = Muted,
        )
        return
    }

    LazyColumn(Modifier.fillMaxSize().padding(horizontal = 20.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        items(reports, key = { it.id }) { report ->
            val timing = report.averageOffsetMs?.let { "   ·   %+.0f ms".format(it) } ?: ""
            SoftCard(Modifier.clickable { openId = report.id }) {
                Text(formatDateTime(report.createdAt), style = MaterialTheme.typography.titleSmall)
                Text("${report.songs.size} songs   ·   %.1f%% avg accuracy".format(report.averageAccuracy * 100) + timing, color = Muted)
            }
        }
    }
}

@Composable
private fun ReportDetailScreen(report: SessionReport, onBack: () -> Unit, onSpeak: (String) -> Unit) {
    Column(
        Modifier.fillMaxSize().padding(20.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        TextButton(onClick = onBack) { Text("← All reports", color = Orange) }
        Text("Session report", style = MaterialTheme.typography.titleLarge)
        Text(formatDateTime(report.createdAt), style = MaterialTheme.typography.bodySmall)
        Text("${report.songs.size} songs   ·   %.1f%% average accuracy".format(report.averageAccuracy * 100))
        PrimaryButton("Read aloud", onClick = { onSpeak(SessionReporter.spoken(report)) })

        Text("Highlights", style = MaterialTheme.typography.titleMedium)
        SoftCard { report.highlights.forEach { Text("•  $it", modifier = Modifier.padding(bottom = 6.dp)) } }

        Text("Songs", style = MaterialTheme.typography.titleMedium)
        report.songs.forEach { song ->
            val timing = song.meanOffsetMs?.let { "   ·   %+.0f ms".format(it) } ?: ""
            SoftCard {
                Text(songLabel(song), style = MaterialTheme.typography.titleSmall)
                Text("%,d   ·   ${song.grade}   ·   %.1f%%".format(song.score, song.accuracy * 100) + timing)
                song.tips.forEach { Text(it, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(top = 4.dp)) }
            }
        }
    }
}
