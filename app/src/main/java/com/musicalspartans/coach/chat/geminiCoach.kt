package com.musicalspartans.coach.chat

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.addJsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

//Real AI chat through Google's Gemini API (free tier key from aistudio.google.com)
class GeminiCoach(private val apiKey: String, private val model: String) : CoachChat {
    override val label = "Gemini AI ($model)"

    override suspend fun reply(history: List<ChatMessage>, context: CoachContext): String =
        withContext(Dispatchers.IO) {
            val body = buildRequest(history, systemPrompt(context)).toString()
            val connection = (URL("$BASE_URL/$model:generateContent").openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                connectTimeout = 15_000
                readTimeout = 60_000
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
                setRequestProperty("x-goog-api-key", apiKey)
            }
            try {
                connection.outputStream.use { it.write(body.toByteArray()) }
                val code = connection.responseCode
                val text = (if (code in 200..299) connection.inputStream else connection.errorStream)
                    ?.bufferedReader()?.use { it.readText() }.orEmpty()
                if (code !in 200..299) throw IOException("Gemini error $code: ${errorMessage(text)}")
                parseReply(text)
            } finally {
                connection.disconnect()
            }
        }

    companion object {
        private const val BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

        fun systemPrompt(context: CoachContext): String = """
            You are the MusicalSpartans rhythm game coach, chatting with the player in a phone app.
            Use the player's analytics below when relevant. Timing/latency is input time minus note time:
            positive means late, negative means early. Accuracy and grades come from the game's scoring
            (Perfect 100%, S 95%+, A 90%+, B 80%+, C 70%+, otherwise Fail).
            Keep answers short (under 120 words) and practical; they may be read aloud.
            You can also answer general questions about rhythm games, practice and music.

            PLAYER DATA:
            ${context.asText()}
        """.trimIndent()

        //Gemini needs the conversation to start with a user message, so leading coach messages are dropped
        fun buildRequest(history: List<ChatMessage>, systemPrompt: String): JsonObject = buildJsonObject {
            putJsonObject("system_instruction") {
                putJsonArray("parts") { addJsonObject { put("text", systemPrompt) } }
            }
            putJsonArray("contents") {
                history.dropWhile { !it.fromUser }.forEach { message ->
                    addJsonObject {
                        put("role", if (message.fromUser) "user" else "model")
                        putJsonArray("parts") { addJsonObject { put("text", message.text) } }
                    }
                }
            }
        }

        fun parseReply(responseJson: String): String {
            val candidates = Json.parseToJsonElement(responseJson).jsonObject["candidates"]?.jsonArray
            val parts = candidates?.firstOrNull()?.jsonObject?.get("content")?.jsonObject?.get("parts")?.jsonArray
            val text = parts?.mapNotNull { it.jsonObject["text"]?.jsonPrimitive?.contentOrNull }?.joinToString("")
            return text?.trim()?.takeIf { it.isNotEmpty() } ?: throw IOException("Gemini returned no text")
        }

        private fun errorMessage(body: String): String = runCatching {
            Json.parseToJsonElement(body).jsonObject["error"]!!.jsonObject["message"]!!.jsonPrimitive.content
        }.getOrDefault(body.take(200))
    }
}
