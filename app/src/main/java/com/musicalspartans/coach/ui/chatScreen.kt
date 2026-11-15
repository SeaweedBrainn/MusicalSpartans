package com.musicalspartans.coach.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.SuggestionChip
import androidx.compose.material3.SuggestionChipDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.ui.graphics.Color
import com.musicalspartans.coach.ui.theme.CardShape
import com.musicalspartans.coach.ui.theme.CardWhite
import com.musicalspartans.coach.ui.theme.Ink
import com.musicalspartans.coach.ui.theme.Line
import com.musicalspartans.coach.ui.theme.Muted
import com.musicalspartans.coach.ui.theme.Orange
import com.musicalspartans.coach.ui.theme.OrangeSoft
import com.musicalspartans.coach.ui.theme.Pill
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.musicalspartans.coach.chat.ChatMessage

private val SUGGESTIONS = listOf(
    "How's my timing?",
    "What should I practice?",
    "Am I improving?",
    "What was my best song?",
    "Summarize my last session",
)

//Chat with the coach about the saved analytics. Tap a coach message to hear it.
@Composable
fun ChatScreen(vm: ChatViewModel, onSpeak: (String) -> Unit) {
    var draft by rememberSaveable { mutableStateOf("") }
    val listState = rememberLazyListState()

    LaunchedEffect(vm.messages.size) {
        listState.animateScrollToItem(vm.messages.lastIndex)
    }

    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().padding(start = 16.dp, end = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(vm.coachLabel, Modifier.weight(1f), style = MaterialTheme.typography.bodySmall)
            TextButton(onClick = vm::clear) { Text("Clear", color = Orange) }
        }

        LazyColumn(
            Modifier.weight(1f).fillMaxWidth(),
            state = listState,
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(vm.messages) { message -> MessageBubble(message, onSpeak) }
            if (vm.sending) item { Text("Coach is typing…", Modifier.padding(horizontal = 16.dp), color = Muted) }
        }

        Row(
            Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            SUGGESTIONS.forEach { s ->
                SuggestionChip(
                    onClick = { vm.send(s) },
                    label = { Text(s) },
                    enabled = !vm.sending,
                    colors = SuggestionChipDefaults.suggestionChipColors(containerColor = CardWhite, labelColor = Ink),
                    border = SuggestionChipDefaults.suggestionChipBorder(enabled = !vm.sending, borderColor = Line),
                )
            }
        }

        Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(
                value = draft,
                onValueChange = { draft = it },
                modifier = Modifier.weight(1f),
                placeholder = { Text("Ask your coach…") },
                maxLines = 4,
                shape = RoundedCornerShape(20.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = Orange,
                    unfocusedBorderColor = Line,
                    focusedContainerColor = CardWhite,
                    unfocusedContainerColor = CardWhite,
                ),
            )
            Button(
                onClick = { vm.send(draft); draft = "" },
                enabled = draft.isNotBlank() && !vm.sending,
                modifier = Modifier.padding(start = 8.dp).height(52.dp),
                shape = Pill,
                colors = ButtonDefaults.buttonColors(containerColor = Orange, disabledContainerColor = OrangeSoft),
            ) { Text("Send") }
        }
    }
}

@Composable
private fun MessageBubble(message: ChatMessage, onSpeak: (String) -> Unit) {
    Box(
        Modifier.fillMaxWidth().padding(horizontal = 12.dp),
        contentAlignment = if (message.fromUser) Alignment.CenterEnd else Alignment.CenterStart,
    ) {
        Card(
            shape = CardShape,
            colors = CardDefaults.cardColors(containerColor = if (message.fromUser) Orange else CardWhite),
            elevation = CardDefaults.cardElevation(if (message.fromUser) 0.dp else 2.dp),
            modifier = Modifier.widthIn(max = 320.dp).let {
                if (message.fromUser) it else it.clickable { onSpeak(message.text) }
            },
        ) {
            Text(message.text, Modifier.padding(14.dp), color = if (message.fromUser) Color.White else Ink)
        }
    }
}
