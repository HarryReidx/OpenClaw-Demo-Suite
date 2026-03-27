package com.tsingyun.openclaw.shell

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Message
import android.provider.MediaStore
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.webkit.CookieManager
import android.webkit.PermissionRequest
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import androidx.core.net.toUri
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.tsingyun.openclaw.shell.databinding.ActivityMainBinding
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private val prefs by lazy { getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE) }

    private var fileChooserCallback: ValueCallback<Array<Uri>>? = null
    private var pendingCameraUri: Uri? = null

    private val fileChooserLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            val callback = fileChooserCallback ?: return@registerForActivityResult
            val uris = when {
                result.resultCode != RESULT_OK -> emptyArray()
                result.data?.clipData != null -> {
                    val clipData = result.data?.clipData
                    Array(clipData?.itemCount ?: 0) { index ->
                        clipData!!.getItemAt(index).uri
                    }
                }
                result.data?.data != null -> arrayOf(result.data!!.data!!)
                pendingCameraUri != null -> arrayOf(pendingCameraUri!!)
                else -> emptyArray()
            }
            callback.onReceiveValue(uris)
            fileChooserCallback = null
            pendingCameraUri = null
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        setSupportActionBar(binding.toolbar)

        configureWebView()

        if (savedInstanceState != null) {
            binding.webView.restoreState(savedInstanceState)
        } else {
            loadOrPromptServerUrl(forcePrompt = false)
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        binding.webView.saveState(outState)
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.main_menu, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        return when (item.itemId) {
            R.id.action_refresh -> {
                binding.webView.reload()
                true
            }
            R.id.action_server -> {
                promptForServerUrl()
                true
            }
            R.id.action_reset -> {
                prefs.edit().remove(KEY_SERVER_URL).apply()
                promptForServerUrl()
                true
            }
            else -> super.onOptionsItemSelected(item)
        }
    }

    override fun onBackPressed() {
        val webView = binding.webView
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }

    private fun configureWebView() {
        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(binding.webView, true)

        binding.webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            allowFileAccess = true
            allowContentAccess = true
            builtInZoomControls = false
            displayZoomControls = false
            cacheMode = WebSettings.LOAD_DEFAULT
            mediaPlaybackRequiresUserGesture = false
            mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
        }

        binding.webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                val uri = request?.url ?: return false
                val scheme = uri.scheme.orEmpty()
                return if (scheme == "http" || scheme == "https") {
                    false
                } else {
                    openExternalUri(uri)
                    true
                }
            }
        }

        binding.webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView?, newProgress: Int) {
                binding.progressBar.progress = newProgress
                binding.progressBar.visibility = if (newProgress >= 100) View.GONE else View.VISIBLE
            }

            override fun onPermissionRequest(request: PermissionRequest?) {
                request?.grant(request.resources)
            }

            override fun onCreateWindow(
                view: WebView?,
                isDialog: Boolean,
                isUserGesture: Boolean,
                resultMsg: Message?,
            ): Boolean {
                val transport = resultMsg?.obj as? WebView.WebViewTransport ?: return false
                transport.webView = binding.webView
                resultMsg.sendToTarget()
                return true
            }

            override fun onShowFileChooser(
                webView: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>?,
                fileChooserParams: FileChooserParams?,
            ): Boolean {
                fileChooserCallback?.onReceiveValue(null)
                fileChooserCallback = filePathCallback
                openFileChooser(fileChooserParams)
                return true
            }
        }
    }

    private fun loadOrPromptServerUrl(forcePrompt: Boolean) {
        val serverUrl = prefs.getString(KEY_SERVER_URL, DEFAULT_SERVER_URL)?.trim().orEmpty()
        if (forcePrompt || serverUrl.isBlank()) {
            promptForServerUrl()
            return
        }
        binding.webView.loadUrl(serverUrl)
    }

    private fun promptForServerUrl() {
        val input = EditText(this).apply {
            setText(prefs.getString(KEY_SERVER_URL, DEFAULT_SERVER_URL) ?: DEFAULT_SERVER_URL)
            hint = "http://192.168.1.20:8105/"
            setSelection(text.length)
        }

        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.server_dialog_title)
            .setMessage(R.string.server_dialog_message)
            .setView(input)
            .setCancelable(false)
            .setPositiveButton(R.string.server_dialog_confirm) { _, _ ->
                val normalized = normalizeServerUrl(input.text?.toString().orEmpty())
                if (normalized == null) {
                    showInvalidUrlDialog()
                } else {
                    prefs.edit().putString(KEY_SERVER_URL, normalized).apply()
                    binding.webView.loadUrl(normalized)
                }
            }
            .setNegativeButton(R.string.server_dialog_default) { _, _ ->
                prefs.edit().putString(KEY_SERVER_URL, DEFAULT_SERVER_URL).apply()
                binding.webView.loadUrl(DEFAULT_SERVER_URL)
            }
            .show()
    }

    private fun showInvalidUrlDialog() {
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.server_invalid_title)
            .setMessage(R.string.server_invalid_message)
            .setPositiveButton(android.R.string.ok) { _, _ -> promptForServerUrl() }
            .show()
    }

    private fun normalizeServerUrl(raw: String): String? {
        if (raw.isBlank()) {
            return null
        }
        val candidate = raw.trim().let { if (it.endsWith("/")) it else "$it/" }
        val uri = runCatching { candidate.toUri() }.getOrNull() ?: return null
        val scheme = uri.scheme?.lowercase(Locale.US)
        return if ((scheme == "http" || scheme == "https") && !uri.host.isNullOrBlank()) {
            candidate
        } else {
            null
        }
    }

    private fun openFileChooser(fileChooserParams: WebChromeClient.FileChooserParams?) {
        val contentIntent = Intent(Intent.ACTION_GET_CONTENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            putExtra(Intent.EXTRA_ALLOW_MULTIPLE, fileChooserParams?.mode == WebChromeClient.FileChooserParams.MODE_OPEN_MULTIPLE)
            type = resolveMimeType(fileChooserParams?.acceptTypes)
            val mimeTypes = resolveMimeTypes(fileChooserParams?.acceptTypes)
            if (mimeTypes.isNotEmpty()) {
                putExtra(Intent.EXTRA_MIME_TYPES, mimeTypes)
            }
        }

        val initialIntents = mutableListOf<Intent>()
        if (acceptsImages(fileChooserParams?.acceptTypes)) {
            createCameraIntent()?.let(initialIntents::add)
        }

        val chooser = Intent(Intent.ACTION_CHOOSER).apply {
            putExtra(Intent.EXTRA_INTENT, contentIntent)
            putExtra(Intent.EXTRA_INITIAL_INTENTS, initialIntents.toTypedArray())
            putExtra(Intent.EXTRA_TITLE, getString(R.string.file_chooser_title))
        }

        runCatching {
            fileChooserLauncher.launch(chooser)
        }.onFailure {
            fileChooserCallback?.onReceiveValue(null)
            fileChooserCallback = null
            pendingCameraUri = null
            Toast.makeText(this, R.string.file_chooser_unavailable, Toast.LENGTH_SHORT).show()
        }
    }

    private fun createCameraIntent(): Intent? {
        val imageFile = createTempImageFile() ?: return null
        val authority = "${applicationContext.packageName}.fileprovider"
        val imageUri = FileProvider.getUriForFile(this, authority, imageFile)
        pendingCameraUri = imageUri
        return Intent(MediaStore.ACTION_IMAGE_CAPTURE).apply {
            putExtra(MediaStore.EXTRA_OUTPUT, imageUri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
        }
    }

    private fun createTempImageFile(): File? {
        val timestamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
        val storageDir = externalCacheDir ?: cacheDir
        return runCatching {
            File.createTempFile("openclaw_${timestamp}_", ".jpg", storageDir)
        }.getOrNull()
    }

    private fun acceptsImages(acceptTypes: Array<String>?): Boolean {
        if (acceptTypes.isNullOrEmpty()) {
            return true
        }
        return acceptTypes.any { type ->
            val normalized = type.trim().lowercase(Locale.US)
            normalized.isBlank() || normalized == "*/*" || normalized.startsWith("image/")
        }
    }

    private fun resolveMimeType(acceptTypes: Array<String>?): String {
        val mimeTypes = resolveMimeTypes(acceptTypes)
        return when {
            mimeTypes.isEmpty() -> "*/*"
            mimeTypes.size == 1 -> mimeTypes.first()
            mimeTypes.all { it.startsWith("image/") } -> "image/*"
            else -> "*/*"
        }
    }

    private fun resolveMimeTypes(acceptTypes: Array<String>?): Array<String> {
        return acceptTypes
            ?.flatMap { it.split(",") }
            ?.map { it.trim() }
            ?.filter { it.isNotBlank() }
            ?.map { if (it == ".txt") "text/plain" else it }
            ?.map { if (it == ".md") "text/markdown" else it }
            ?.map { if (it == ".docx") DOCX_MIME_TYPE else it }
            ?.distinct()
            ?.toTypedArray()
            ?: emptyArray()
    }

    private fun openExternalUri(uri: Uri) {
        val intent = Intent(Intent.ACTION_VIEW, uri)
        try {
            startActivity(intent)
        } catch (_: ActivityNotFoundException) {
            Toast.makeText(this, R.string.external_open_failed, Toast.LENGTH_SHORT).show()
        }
    }

    companion object {
        private const val PREFS_NAME = "openclaw_shell_prefs"
        private const val KEY_SERVER_URL = "server_url"
        private const val DEFAULT_SERVER_URL = "http://10.0.2.2:8105/"
        private const val DOCX_MIME_TYPE =
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    }
}
