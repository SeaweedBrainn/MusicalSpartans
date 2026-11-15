package com.musicalspartans.coach.model

import kotlinx.serialization.Serializable
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

//Small per-song summary kept after the detailed song data is thrown away
/**
 * playedAt - when the song was imported (epoch ms)
 * grade - Perfect, S, A, B, C, Fail
 * meanOffsetMs - average timing (negative = early), null if unknown
 * weakestSection... - the section with the lowest accuracy, null without timeline data
 * tips - coaching tips as text, e.g. "0:05 you sped up..."
 */
@Serializable
data class SongSummary(
    val songId: Int,
    val chartId: Int,
    val difficulty: Int,
    val playedAt: Long,
    val score: Int,
    val grade: String,
    val accuracy: Double,
    val totalNotes: Int,
    val gameTimeMs: Long,
    val bpm: Int,
    val meanOffsetMs: Double?,
    val weakestSectionStartMs: Long?,
    val weakestSectionAccuracy: Double?,
    val tips: List<String>,
)

//Saved permanently on the phone. Built from all songs in one session.
/**
 * averageAccuracy - 0.0 to 1.0 across all songs
 * averageOffsetMs - average timing across songs (negative = early)
 * highlights - short sentences about the session (best song, trend, timing)
 */
@Serializable
data class SessionReport(
    val id: String,
    val createdAt: Long,
    val songs: List<SongSummary>,
    val averageAccuracy: Double,
    val averageOffsetMs: Double?,
    val highlights: List<String>,
)


fun songLabel(s: SongSummary): String = "Song ${s.songId} (${difficultyName(s.difficulty)})"

private val dateTimeFormat = DateTimeFormatter.ofPattern("MMM d, yyyy h:mm a")

fun formatDateTime(epochMs: Long): String =
    dateTimeFormat.format(Instant.ofEpochMilli(epochMs).atZone(ZoneId.systemDefault()))
