package com.musicalspartans.coach.ui

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.musicalspartans.coach.BuildConfig
import com.musicalspartans.coach.chat.ChatMessage
import com.musicalspartans.coach.chat.CoachChat
import com.musicalspartans.coach.chat.CoachContext
import com.musicalspartans.coach.chat.GeminiCoach
import com.musicalspartans.coach.chat.OfflineCoach
import com.musicalspartans.coach.data.SessionStore
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class ChatViewModel(app: Application) : AndroidViewModel(app) {
    private val store = SessionStore(app.filesDir)
    private val offline = OfflineCoach()

    //Uses Gemini when gemini.apiKey is set in local.properties, otherwise the offline coach
    private val coach: CoachChat =
        if (BuildConfig.GEMINI_API_KEY.isNotBlank()) GeminiCoach(BuildConfig.GEMINI_API_KEY, BuildConfig.GEMINI_MODEL)
        else offline

    val coachLabel: String get() = coach.label

    var messages by mutableStateOf(
        listOf(ChatMessage(false, "Hi! I'm your coach. Ask me about your timing, your best songs, or what to practice."))
    )
        private set
    var sending by mutableStateOf(false)
        private set

    fun send(text: String) {
        val question = text.trim()
        if (question.isEmpty() || sending) return
        messages = messages + ChatMessage(true, question)
        sending = true

        viewModelScope.launch {
            val history = messages
            val answer = try {
                val context = withContext(Dispatchers.IO) { CoachContext(store.reports(), store.currentSession()) }
                try {
                    coach.reply(history, context)
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    if (coach === offline) throw e
                    "(AI unavailable: ${e.message}. Answering offline.)\n\n" + offline.reply(history, context)
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                "Sorry, something went wrong: ${e.message}"
            }
            messages = messages + ChatMessage(false, answer)
            sending = false
        }
    }

    fun clear() {
        messages = messages.take(1)
    }
}
