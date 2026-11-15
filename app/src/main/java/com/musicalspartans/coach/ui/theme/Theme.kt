package com.musicalspartans.coach.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val LightColors = lightColorScheme(
    primary = Orange,
    onPrimary = Color.White,
    primaryContainer = OrangeSoft,
    onPrimaryContainer = OrangePressed,
    secondary = OrangePressed,
    onSecondary = Color.White,
    background = Peach,
    onBackground = Ink,
    surface = CardWhite,
    onSurface = Ink,
    surfaceVariant = OrangeSoft,
    onSurfaceVariant = Muted,
    outline = Line,
)

@Composable
fun MusicalSpartansTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = LightColors,
        typography = Typography,
        content = content,
    )
}
