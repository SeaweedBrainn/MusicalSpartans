package com.musicalspartans.coach.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.MediaItem
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import com.musicalspartans.coach.model.Guide
import com.musicalspartans.coach.model.Run
import com.musicalspartans.coach.model.formatTime
import kotlinx.coroutines.delay

@Composable
fun ReplayScreen(run: Run, tips: List<Guide>, onBack: () -> Unit) {
    val context = LocalContext.current

    //Create the video player once and release it when leaving the screen
    val player = remember {
        ExoPlayer.Builder(context).build().apply {
            setMediaItem(MediaItem.fromUri(run.videoURI))
            prepare()
        }
    }
    DisposableEffect(player) { onDispose { player.release() } }

    //Song time = video time minus where the song starts in the video
    var songPositionMs by remember { mutableLongStateOf(0L) }
    LaunchedEffect(player) {
        while (true) {
            songPositionMs = player.currentPosition - run.videoOffsetMs
            delay(250)
        }
    }
    //A section tip is highlighted only during its 5 second window.
    //A whole-song tip (spansSong) is advice about the run, not a moment in the video.
    val activeTip = tips.lastOrNull { tip ->
        !tip.spansSong && songPositionMs in tip.timeMs until tip.timeMs + 5_000
    }

    var slowMo by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize()) {
        TextButton(onClick = onBack, modifier = Modifier.padding(horizontal = 8.dp)) {
            Text("← Back to results", color = com.musicalspartans.coach.ui.theme.Orange)
        }

        AndroidView(
            factory = { PlayerView(it).apply { this.player = player } },
            modifier = Modifier.fillMaxWidth().aspectRatio(16f / 9f),
        )

        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("Slow motion (0.5x)", Modifier.weight(1f))
            Switch(checked = slowMo, onCheckedChange = {
                slowMo = it
                player.setPlaybackSpeed(if (it) 0.5f else 1f)
            })
        }

        //Tap a tip to jump the video to that moment
        LazyColumn {
            items(tips) { tip ->
                ListItem(
                    overlineContent = { Text(formatTime(tip.timeMs)) },
                    headlineContent = { Text(tip.text) },
                    colors = ListItemDefaults.colors(
                        containerColor = if (tip == activeTip) com.musicalspartans.coach.ui.theme.OrangeSoft
                        else com.musicalspartans.coach.ui.theme.CardWhite,
                    ),
                    modifier = Modifier.clickable {
                        player.seekTo(tip.timeMs + run.videoOffsetMs)
                        player.play()
                    },
                )
            }
        }
    }
}