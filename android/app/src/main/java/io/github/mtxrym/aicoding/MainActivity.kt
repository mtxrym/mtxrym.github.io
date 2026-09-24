package io.github.mtxrym.aicoding

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.lifecycle.viewmodel.compose.viewModel
import io.github.mtxrym.aicoding.ui.FeedScreen
import io.github.mtxrym.aicoding.ui.FeedViewModel
import io.github.mtxrym.aicoding.ui.theme.AICodingTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        setContent {
            AICodingTheme {
                val viewModel: FeedViewModel = viewModel()
                FeedScreen(viewModel)
            }
        }
    }
}
