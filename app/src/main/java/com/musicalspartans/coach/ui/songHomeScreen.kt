package com.musicalspartans.coach.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.musicalspartans.coach.model.SongSummary
import com.musicalspartans.coach.model.formatDateTime
import com.musicalspartans.coach.model.songLabel
import com.musicalspartans.coach.ui.theme.Muted
import com.musicalspartans.coach.ui.theme.Orange
import com.musicalspartans.coach.ui.theme.PrimaryButton
import com.musicalspartans.coach.ui.theme.SecondaryButton
import com.musicalspartans.coach.ui.theme.SoftCard

@Composable
fun SongHomeScreen(
    currentSession: List<SongSummary>,
    busy: Boolean,
    onImport: () -> Unit,
    onSample: () -> Unit,
    onGenerateReport: () -> Unit,
) {
    Column(
        Modifier.fillMaxSize().padding(20.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        if (busy) LinearProgressIndicator(Modifier.fillMaxWidth(), color = Orange)

        Text("New song", style = MaterialTheme.typography.titleLarge)
        Text(
            "Pick the game's files for one song: the summary CSV and the timeline CSV. The summary alone also works, but without per-section stats.",
            style = MaterialTheme.typography.bodyMedium,
            color = Muted,
        )
        PrimaryButton("Import song files", onImport, enabled = !busy)
        SecondaryButton("Load sample song", onSample, enabled = !busy)

        Text("Current session", style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(top = 8.dp))
        if (currentSession.isEmpty()) {
            SoftCard { Text("No songs yet. Each song you import is summarized and added here.", color = Muted) }
        } else {
            currentSession.forEach { song ->
                SoftCard {
                    Text(songLabel(song), style = MaterialTheme.typography.titleSmall)
                    Text("%,d   ·   ${song.grade}   ·   %.1f%%".format(song.score, song.accuracy * 100))
                    Text(formatDateTime(song.playedAt), style = MaterialTheme.typography.bodySmall)
                }
            }
        }
        PrimaryButton(
            "Generate session report (${currentSession.size} songs)",
            onGenerateReport,
            enabled = currentSession.isNotEmpty() && !busy,
        )
        Text(
            "The report is saved on this phone, and the current session starts over.",
            style = MaterialTheme.typography.bodySmall,
        )
    }
}
