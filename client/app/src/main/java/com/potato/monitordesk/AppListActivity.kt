package com.potato.monitordesk

import android.content.Intent
import android.os.Bundle
import android.view.Gravity
import android.widget.ArrayAdapter
import android.widget.ListView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

private data class AppEntry(val label: String, val packageName: String)

/**
 * Daftar aplikasi terpasang di HP. Centang app yang notifnya mau
 * disunyikan selama Potato Monitor Desk dipakai (mis. WhatsApp, Telegram,
 * Instagram). App yang tidak dicentang (mis. app live-streaming kamu)
 * tetap tampil notifikasinya seperti biasa.
 */
class AppListActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val ownPackage = packageName
        val pm = packageManager
        val launcherIntent = Intent(Intent.ACTION_MAIN, null).addCategory(Intent.CATEGORY_LAUNCHER)

        val apps = pm.queryIntentActivities(launcherIntent, 0)
            .map { AppEntry(it.loadLabel(pm).toString(), it.activityInfo.packageName) }
            .filter { it.packageName != ownPackage }
            .distinctBy { it.packageName }
            .sortedBy { it.label.lowercase() }

        val blocked = NotificationPrefs.getBlockedPackages(this).toMutableSet()

        val header = TextView(this).apply {
            text = "Centang aplikasi yang notifnya ingin disunyikan\nsaat Potato Monitor Desk aktif:"
            setPadding(32, 32, 32, 16)
            gravity = Gravity.START
        }

        val listView = ListView(this)
        val labels = apps.map { it.label }
        val adapter = ArrayAdapter(this, android.R.layout.simple_list_item_multiple_choice, labels)
        listView.adapter = adapter
        listView.choiceMode = ListView.CHOICE_MODE_MULTIPLE

        apps.forEachIndexed { index, app ->
            if (blocked.contains(app.packageName)) {
                listView.setItemChecked(index, true)
            }
        }

        listView.setOnItemClickListener { _, _, position, _ ->
            val app = apps[position]
            if (listView.isItemChecked(position)) {
                blocked.add(app.packageName)
            } else {
                blocked.remove(app.packageName)
            }
            NotificationPrefs.setBlockedPackages(this, blocked)
        }

        val root = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            addView(header)
            addView(listView)
        }
        setContentView(root)
    }
}
