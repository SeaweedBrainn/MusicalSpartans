package com.musicalspartans.coach.ui

import android.app.Application
import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.musicalspartans.coach.analytics.Analyzer
import com.musicalspartans.coach.analytics.SessionReporter
import com.musicalspartans.coach.data.FakeRunRepository
import com.musicalspartans.coach.data.RunImporter
import com.musicalspartans.coach.data.SAMPLE_RUN_ID
import com.musicalspartans.coach.data.SessionStore
import com.musicalspartans.coach.data.localDayBounds
import com.musicalspartans.coach.model.PostGameAnalysis
import com.musicalspartans.coach.model.Run
import com.musicalspartans.coach.model.SessionReport
import com.musicalspartans.coach.model.SongSummary
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

//The song currently on screen. Only kept in memory: it's gone after "Done with song".
data class LoadedSong(val run: Run, val analysis: PostGameAnalysis, val source: String)

//Songs, the current session and saved reports
class CoachViewModel(private val app: Application) : AndroidViewModel(app) {
    private val store = SessionStore(app.filesDir)

    var currentSong by mutableStateOf<LoadedSong?>(null)
        private set
    var currentSession by mutableStateOf<List<SongSummary>>(emptyList())
        private set
    var reports by mutableStateOf<List<SessionReport>>(emptyList())
        private set
    var busy by mutableStateOf(false)
        private set
    //One-off notice shown at the bottom of the screen
    var message by mutableStateOf<String?>(null)
        private set
    var showReplay by mutableStateOf(false)
        private set

    init {
        task { reloadLists() }
    }

    fun importFiles(uris: List<Uri>) {
        if (uris.isEmpty()) return
        task {
            val texts = withContext(Dispatchers.IO) {
                uris.map { uri ->
                    app.contentResolver.openInputStream(uri)?.bufferedReader()?.use { it.readText() }
                        ?: error("Couldn't open $uri")
                }
            }
            openSong(RunImporter.fromTexts(texts), "Imported from files")
        }
    }

    fun loadSample() = task {
        openSong(FakeRunRepository(app).loadRun(SAMPLE_RUN_ID), "Sample song")
    }

    //Detailed song data is dropped; its summary is already in the current session
    fun finishSong() {
        currentSong = null
        showReplay = false
    }

    fun openReplay() {
        showReplay = true
    }

    fun closeReplay() {
        showReplay = false
    }

    fun generateReport() = task {
        val report = withContext(Dispatchers.IO) {
            val songs = store.currentSession()
            SessionReporter.build(songs, System.currentTimeMillis()).also {
                store.saveReport(it)
                store.clearSession()
            }
        }
        currentSong = null
        showReplay = false
        reloadLists()
        message = "Session report saved (${report.songs.size} songs). See the Reports tab."
    }

    fun clearSession() = task {
        withContext(Dispatchers.IO) { store.clearSession() }
        currentSong = null
        showReplay = false
        reloadLists()
        message = "Current session cleared."
    }

    //startUtcMs/endUtcMs come straight from the date range picker
    fun deleteReports(startUtcMs: Long, endUtcMs: Long) = task {
        val (from, to) = localDayBounds(startUtcMs, endUtcMs)
        val deleted = withContext(Dispatchers.IO) { store.deleteReports(from, to) }
        reloadLists()
        message = "Deleted $deleted report${if (deleted == 1) "" else "s"}."
    }

    fun deleteAllReports() = task {
        val deleted = withContext(Dispatchers.IO) { store.deleteAllReports() }
        reloadLists()
        message = "Deleted $deleted report${if (deleted == 1) "" else "s"}."
    }

    fun dismissMessage() {
        message = null
    }

    private suspend fun openSong(run: Run, source: String) {
        val analysis = Analyzer.analyze(run)
        val summary = SessionReporter.songSummary(run, analysis, System.currentTimeMillis())
        withContext(Dispatchers.IO) { store.addSong(summary) }
        showReplay = false
        currentSong = LoadedSong(run, analysis, source)
        reloadLists()
    }

    private suspend fun reloadLists() {
        val (session, saved) = withContext(Dispatchers.IO) { store.currentSession() to store.reports() }
        currentSession = session
        reports = saved
    }

    private fun task(block: suspend () -> Unit) {
        viewModelScope.launch {
            busy = true
            try {
                block()
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                message = e.message ?: e.toString()
            } finally {
                busy = false
            }
        }
    }
}
