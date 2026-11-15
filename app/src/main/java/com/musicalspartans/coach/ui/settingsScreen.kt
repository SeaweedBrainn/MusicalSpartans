package com.musicalspartans.coach.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.DateRangePicker
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDateRangePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.musicalspartans.coach.ui.theme.Muted
import com.musicalspartans.coach.ui.theme.PrimaryButton
import com.musicalspartans.coach.ui.theme.SecondaryButton
import com.musicalspartans.coach.ui.theme.SoftCard

private enum class Confirm { DELETE_ALL, CLEAR_SESSION }

@Composable
fun SettingsScreen(
    reportCount: Int,
    sessionSongCount: Int,
    coachLabel: String,
    onDeleteRange: (startUtcMs: Long, endUtcMs: Long) -> Unit,
    onDeleteAll: () -> Unit,
    onClearSession: () -> Unit,
) {
    var showRangePicker by rememberSaveable { mutableStateOf(false) }
    var confirm by rememberSaveable { mutableStateOf<Confirm?>(null) }

    Column(
        Modifier.fillMaxSize().padding(20.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text("Saved session reports ($reportCount)", style = MaterialTheme.typography.titleLarge)
        Text("Reports are stored only on this phone. Remove the ones you don't need.", color = Muted)
        PrimaryButton("Delete reports in a date range", { showRangePicker = true }, enabled = reportCount > 0)
        SecondaryButton("Delete all reports", { confirm = Confirm.DELETE_ALL }, enabled = reportCount > 0)

        Text("Current session ($sessionSongCount songs)", style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(top = 8.dp))
        SecondaryButton("Discard current session without a report", { confirm = Confirm.CLEAR_SESSION }, enabled = sessionSongCount > 0)

        Text("AI coach", style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(top = 8.dp))
        SoftCard {
            Text("Using", color = Muted, style = MaterialTheme.typography.bodySmall)
            Text(coachLabel, style = MaterialTheme.typography.titleSmall)
        }
        Text(
            "The offline coach answers questions about your stats with no internet. For full conversations, " +
                    "get a free Gemini API key at aistudio.google.com, add the line gemini.apiKey=YOUR_KEY " +
                    "to local.properties in the project folder, and rebuild the app.",
            style = MaterialTheme.typography.bodySmall,
        )
    }

    if (showRangePicker) {
        DeleteRangeDialog(
            onDismiss = { showRangePicker = false },
            onConfirm = { start, end ->
                showRangePicker = false
                onDeleteRange(start, end)
            },
        )
    }

    when (confirm) {
        Confirm.DELETE_ALL -> ConfirmDialog(
            text = "Delete all $reportCount saved session reports? This can't be undone.",
            onDismiss = { confirm = null },
            onConfirm = { confirm = null; onDeleteAll() },
        )
        Confirm.CLEAR_SESSION -> ConfirmDialog(
            text = "Discard the $sessionSongCount songs in the current session without saving a report?",
            onDismiss = { confirm = null },
            onConfirm = { confirm = null; onClearSession() },
        )
        null -> Unit
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DeleteRangeDialog(onDismiss: () -> Unit, onConfirm: (Long, Long) -> Unit) {
    val state = rememberDateRangePickerState()
    val start = state.selectedStartDateMillis
    DatePickerDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            TextButton(enabled = start != null, onClick = { start?.let { onConfirm(it, state.selectedEndDateMillis ?: it) } }) {
                Text("Delete")
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    ) {
        DateRangePicker(
            state = state,
            title = { Text("Delete reports from these days", Modifier.padding(start = 24.dp, top = 16.dp)) },
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun ConfirmDialog(text: String, onDismiss: () -> Unit, onConfirm: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        text = { Text(text) },
        confirmButton = { TextButton(onClick = onConfirm) { Text("Delete") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
