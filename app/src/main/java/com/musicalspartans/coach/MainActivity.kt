package com.musicalspartans.coach

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Snackbar
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.lifecycle.viewmodel.compose.viewModel
import com.musicalspartans.coach.analytics.Analyzer
import com.musicalspartans.coach.speech.Speaker
import com.musicalspartans.coach.ui.ChatScreen
import com.musicalspartans.coach.ui.ChatViewModel
import com.musicalspartans.coach.ui.CoachViewModel
import com.musicalspartans.coach.ui.ReplayScreen
import com.musicalspartans.coach.ui.ReportsScreen
import com.musicalspartans.coach.ui.ResultsScreen
import com.musicalspartans.coach.ui.SettingsScreen
import com.musicalspartans.coach.ui.SongHomeScreen
import com.musicalspartans.coach.ui.theme.CardWhite
import com.musicalspartans.coach.ui.theme.Ink
import com.musicalspartans.coach.ui.theme.MusicalSpartansTheme
import com.musicalspartans.coach.ui.theme.Muted
import com.musicalspartans.coach.ui.theme.Orange
import com.musicalspartans.coach.ui.theme.OrangeSoft
import com.musicalspartans.coach.ui.theme.Peach

private enum class Tab(val label: String, val glyph: String) {
    SONG("Song", "♪"),
    REPORTS("Reports", "☰"),
    COACH("Coach", "💬"),
    SETTINGS("Settings", "⚙"),
}

//CSV files show up under several MIME types depending on the file app
private val CSV_TYPES = arrayOf("text/*", "application/csv", "application/vnd.ms-excel", "application/octet-stream")

class MainActivity : ComponentActivity() {
    private lateinit var speaker: Speaker

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        speaker = Speaker(this)

        setContent {
            MusicalSpartansTheme {
                App(speak = speaker::speak)
            }
        }
    }

    override fun onDestroy() {
        speaker.shutdown()
        super.onDestroy()
    }
}

@Composable
private fun App(speak: (String) -> Unit) {
    val vm: CoachViewModel = viewModel()
    val chatVm: ChatViewModel = viewModel()
    var tab by rememberSaveable { mutableStateOf(Tab.SONG) }
    val snackbar = remember { SnackbarHostState() }

    val pickFiles = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        vm.importFiles(uris)
    }

    LaunchedEffect(vm.message) {
        vm.message?.let {
            snackbar.showSnackbar(it)
            vm.dismissMessage()
        }
    }

    Scaffold(
        Modifier.fillMaxSize(),
        containerColor = Peach,
        snackbarHost = {
            SnackbarHost(snackbar) { data ->
                Snackbar(data, containerColor = Ink, contentColor = Color.White)
            }
        },
        bottomBar = {
            NavigationBar(containerColor = CardWhite) {
                Tab.entries.forEach { t ->
                    NavigationBarItem(
                        selected = tab == t,
                        onClick = { tab = t },
                        icon = { Text(t.glyph, color = if (tab == t) Orange else Muted) },
                        label = { Text(t.label) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedTextColor = Orange,
                            unselectedTextColor = Muted,
                            indicatorColor = OrangeSoft,
                        ),
                    )
                }
            }
        },
    ) { padding ->
        Box(Modifier.padding(padding).consumeWindowInsets(padding).imePadding()) {
            when (tab) {
                Tab.SONG -> {
                    val song = vm.currentSong
                    when {
                        song == null -> SongHomeScreen(
                            currentSession = vm.currentSession,
                            busy = vm.busy,
                            onImport = { pickFiles.launch(CSV_TYPES) },
                            onSample = vm::loadSample,
                            onGenerateReport = vm::generateReport,
                        )
                        vm.showReplay -> {
                            BackHandler { vm.closeReplay() }
                            ReplayScreen(song.run, song.analysis.tips, onBack = vm::closeReplay)
                        }
                        else -> {
                            BackHandler { vm.finishSong() }
                            ResultsScreen(
                                run = song.run,
                                analysis = song.analysis,
                                source = song.source,
                                onSpeak = { speak(Analyzer.spokenSummary(song.analysis)) },
                                onOpenReplay = vm::openReplay,
                                onDone = vm::finishSong,
                            )
                        }
                    }
                }
                Tab.REPORTS -> ReportsScreen(vm.reports, onSpeak = speak)
                Tab.COACH -> ChatScreen(chatVm, onSpeak = speak)
                Tab.SETTINGS -> SettingsScreen(
                    reportCount = vm.reports.size,
                    sessionSongCount = vm.currentSession.size,
                    coachLabel = chatVm.coachLabel,
                    onDeleteRange = vm::deleteReports,
                    onDeleteAll = vm::deleteAllReports,
                    onClearSession = vm::clearSession,
                )
            }
        }
    }
}
