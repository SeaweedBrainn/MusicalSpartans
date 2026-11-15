package com.musicalspartans.coach.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import com.musicalspartans.coach.R

val Calibri = FontFamily(
    Font(R.font.calibri_regular, FontWeight.Normal),
    Font(R.font.calibri_bold, FontWeight.Bold),
    Font(R.font.calibri_italic, FontWeight.Normal, FontStyle.Italic),
)

private fun style(weight: FontWeight, size: Int, line: Int) = TextStyle(
    fontFamily = Calibri,
    fontWeight = weight,
    fontSize = size.sp,
    lineHeight = line.sp,
)

val Typography = Typography(
    displayMedium = style(FontWeight.Bold, 44, 50),
    headlineMedium = style(FontWeight.Bold, 28, 34),
    titleLarge = style(FontWeight.Bold, 22, 28),
    titleMedium = style(FontWeight.Bold, 18, 24),
    titleSmall = style(FontWeight.Bold, 16, 22),
    bodyLarge = style(FontWeight.Normal, 16, 24),
    bodyMedium = style(FontWeight.Normal, 15, 22),
    bodySmall = style(FontWeight.Normal, 13, 18).copy(color = Muted),
    labelLarge = style(FontWeight.Bold, 15, 20),
)
