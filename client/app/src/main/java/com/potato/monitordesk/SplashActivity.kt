package com.potato.monitordesk

import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.FrameLayout
import android.widget.ImageView
import androidx.appcompat.app.AppCompatActivity

/**
 * Splash screen sederhana: tampilkan logo Potato Monitor Desk sebentar,
 * lalu lanjut ke MainActivity. Tidak pakai library tambahan supaya tetap ringan.
 */
class SplashActivity : AppCompatActivity() {

    companion object {
        private const val SPLASH_DELAY_MS = 1200L
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val root = FrameLayout(this).apply {
            setBackgroundColor(0xFF111111.toInt())
        }
        val logo = ImageView(this).apply {
            setImageResource(R.drawable.potato_logo)
            adjustViewBounds = true
        }
        val logoParams = FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.WRAP_CONTENT,
            FrameLayout.LayoutParams.WRAP_CONTENT
        ).apply { gravity = android.view.Gravity.CENTER }
        root.addView(logo, logoParams)
        setContentView(root)

        Handler(Looper.getMainLooper()).postDelayed({
            startActivity(Intent(this, MainActivity::class.java))
            finish()
        }, SPLASH_DELAY_MS)
    }
}
