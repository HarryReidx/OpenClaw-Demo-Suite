package com.openclaw.mobile

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.MediaStore
import android.view.LayoutInflater
import android.view.View
import android.webkit.CookieManager
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import com.google.android.material.button.MaterialButton
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.textfield.TextInputEditText
import java.io.File
import java.util.Locale

class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var progressBar: ProgressBar
    private lateinit var currentUrlText: TextView
    private lateinit var errorPanel: View
    private lateinit var errorMessageText: TextView

    private val prefs by lazy { getSharedPreferences(PREFS_NAME, MODE_PRIVATE) }

    private var filePathCallback: ValueCallback<Array<Uri>>? = null
    private var cameraOutputUri: Uri? = null

    private val fileChooserLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            handleFileChooserResult(result.resultCode, result.data)
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        webView = findViewById(R.id.webView)
        progressBar = findViewById(R.id.progressBar)
        currentUrlText = findViewById(R.id.textCurrentUrl)
        errorPanel = findViewById(R.id.errorPanel)
        errorMessageText = findViewById(R.id.textErrorMessage)

        val configureButton = findViewById<MaterialButton>(R.id.buttonConfigure)
        val configureErrorButton = findViewById<MaterialButton>(R.id.buttonConfigureError)
        val reloadButton = findViewById<MaterialButton>(R.id.buttonReload)
        val retryButton = findViewById<MaterialButton>(R.id.buttonRetry)

        configureButton.setOnClickListener { showBackendDialog() }
        configureErrorButton.setOnClickListener { showBackendDialog() }
        reloadButton.setOnClickListener {
            hideError()
            if (webView.url.isNullOrBlank()) {
                webView.loadUrl(configuredEntryUrl())
            } else {
                webView.reload()
            }
        }
        retryButton.setOnClickListener {
            hideError()
            webView.loadUrl(configuredEntryUrl())
        }

        setupWebView()
        updateCurrentUrlLabel(getConfiguredBaseUrl())
        setupBackHandler()

        if (savedInstanceState != null) {
            webView.restoreState(savedInstanceState)
        } else {
            webView.loadUrl(configuredEntryUrl())
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        webView.saveState(outState)
        super.onSaveInstanceState(outState)
    }

    override fun onDestroy() {
        filePathCallback?.onReceiveValue(null)
        filePathCallback = null
        webView.stopLoading()
        webView.webChromeClient = null
        webView.destroy()
        super.onDestroy()
    }

    private fun setupBackHandler() {
        onBackPressedDispatcher.addCallback(
            this,
            object : OnBackPressedCallback(true) {
                override fun handleOnBackPressed() {
                    if (webView.canGoBack()) {
                        webView.goBack()
                    } else {
                        finish()
                    }
                }
            },
        )
    }

    private fun setupWebView() {
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)

        with(webView.settings) {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            allowFileAccess = true
            allowContentAccess = true
            mediaPlaybackRequiresUserGesture = false
            setSupportZoom(false)
            builtInZoomControls = false
            displayZoomControls = false
            cacheMode = WebSettings.LOAD_DEFAULT
            mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
        }

        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true)

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                val target = request?.url ?: return false
                val scheme = target.scheme?.lowercase(Locale.US) ?: return false
                if (scheme == "http" || scheme == "https") {
                    return false
                }
                return launchExternalApp(target)
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                hideError()
                progressBar.visibility = View.GONE
                updateCurrentUrlLabel(extractBaseUrl(url) ?: getConfiguredBaseUrl())
                disableTapHighlight()
                super.onPageFinished(view, url)
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?,
            ) {
                if (request?.isForMainFrame == true) {
                    val message = error?.description?.toString().orEmpty().ifBlank {
                        getString(R.string.error_message)
                    }
                    showError(message)
                }
                super.onReceivedError(view, request, error)
            }

            override fun onReceivedHttpError(
                view: WebView?,
                request: WebResourceRequest?,
                errorResponse: WebResourceResponse?,
            ) {
                if (request?.isForMainFrame == true && errorResponse?.statusCode != null) {
                    showError("HTTP ${errorResponse.statusCode}")
                }
                super.onReceivedHttpError(view, request, errorResponse)
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView?, newProgress: Int) {
                progressBar.progress = newProgress
                progressBar.visibility = if (newProgress in 1..99) View.VISIBLE else View.GONE
                super.onProgressChanged(view, newProgress)
            }

            override fun onShowFileChooser(
                webView: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>,
                fileChooserParams: FileChooserParams,
            ): Boolean {
                return launchFileChooser(filePathCallback, fileChooserParams)
            }
        }
    }

    private fun showBackendDialog() {
        val dialogView = LayoutInflater.from(this).inflate(R.layout.dialog_backend_url, null)
        val editBaseUrl = dialogView.findViewById<TextInputEditText>(R.id.editBaseUrl)
        editBaseUrl.setText(getConfiguredBaseUrl())

        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.backend_dialog_title)
            .setView(dialogView)
            .setNegativeButton(R.string.backend_dialog_cancel, null)
            .setNeutralButton(R.string.backend_dialog_reset) { _, _ ->
                saveBackendUrl(normalizeBaseUrl(BuildConfig.DEFAULT_BASE_URL))
                hideError()
                webView.loadUrl(configuredEntryUrl())
            }
            .setPositiveButton(R.string.backend_dialog_save) { _, _ ->
                val normalized = normalizeBaseUrl(editBaseUrl.text?.toString().orEmpty())
                saveBackendUrl(normalized)
                hideError()
                webView.loadUrl("$normalized/")
            }
            .show()
    }

    private fun launchFileChooser(
        callback: ValueCallback<Array<Uri>>,
        params: WebChromeClient.FileChooserParams,
    ): Boolean {
        filePathCallback?.onReceiveValue(null)
        filePathCallback = callback
        cameraOutputUri = null

        val acceptTypes = sanitizeAcceptTypes(params.acceptTypes)
        val pickerIntent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = resolvePickerMimeType(acceptTypes)
            if (acceptTypes.isNotEmpty()) {
                putExtra(Intent.EXTRA_MIME_TYPES, acceptTypes.toTypedArray())
            }
            putExtra(
                Intent.EXTRA_ALLOW_MULTIPLE,
                params.mode == WebChromeClient.FileChooserParams.MODE_OPEN_MULTIPLE,
            )
        }

        val extraIntents = mutableListOf<Intent>()
        if (shouldOfferCamera(acceptTypes)) {
            createCameraIntent()?.let(extraIntents::add)
        }

        val chooserIntent = Intent(Intent.ACTION_CHOOSER).apply {
            putExtra(Intent.EXTRA_INTENT, pickerIntent)
            putExtra(Intent.EXTRA_TITLE, getString(R.string.file_chooser_title))
            putExtra(Intent.EXTRA_INITIAL_INTENTS, extraIntents.toTypedArray())
        }

        return try {
            fileChooserLauncher.launch(chooserIntent)
            true
        } catch (_: ActivityNotFoundException) {
            filePathCallback = null
            cameraOutputUri = null
            Toast.makeText(this, "No file picker found on device.", Toast.LENGTH_SHORT).show()
            false
        }
    }

    private fun createCameraIntent(): Intent? {
        val cacheRoot = externalCacheDir ?: cacheDir
        val imageFile = File.createTempFile("openclaw_capture_", ".jpg", cacheRoot)
        val uri = FileProvider.getUriForFile(
            this,
            "${BuildConfig.APPLICATION_ID}.fileprovider",
            imageFile,
        )
        cameraOutputUri = uri

        val intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE).apply {
            putExtra(MediaStore.EXTRA_OUTPUT, uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
        }

        val activities = packageManager.queryIntentActivities(intent, 0)
        if (activities.isEmpty()) {
            cameraOutputUri = null
            return null
        }

        activities.forEach { resolveInfo ->
            grantUriPermission(
                resolveInfo.activityInfo.packageName,
                uri,
                Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION,
            )
        }

        return intent
    }

    private fun handleFileChooserResult(resultCode: Int, data: Intent?) {
        val callback = filePathCallback ?: return
        var result: Array<Uri>? = null

        if (resultCode == RESULT_OK) {
            result = when {
                data?.clipData != null -> {
                    val clipData = data.clipData!!
                    Array(clipData.itemCount) { index -> clipData.getItemAt(index).uri }
                }

                data?.data != null -> arrayOf(data.data!!)
                cameraOutputUri != null -> arrayOf(cameraOutputUri!!)
                else -> null
            }
        }

        callback.onReceiveValue(result)
        filePathCallback = null
        cameraOutputUri = null
    }

    private fun launchExternalApp(uri: Uri): Boolean {
        return try {
            startActivity(Intent(Intent.ACTION_VIEW, uri))
            true
        } catch (_: ActivityNotFoundException) {
            false
        }
    }

    private fun disableTapHighlight() {
        webView.evaluateJavascript(
            """
            (function () {
                try {
                    var styleId = 'openclaw-android-touch-fixes';
                    if (!document.getElementById(styleId)) {
                        var style = document.createElement('style');
                        style.id = styleId;
                        style.textContent =
                            '*,' +
                            '*::before,' +
                            '*::after{' +
                            '-webkit-tap-highlight-color: transparent !important;' +
                            '}' +
                            'button,a,input,textarea,select,[role="button"],.chip,.menu-item{' +
                            'outline: none !important;' +
                            'box-shadow: none !important;' +
                            '}' +
                            'textarea{' +
                            'min-height: 88px !important;' +
                            'height: 88px !important;' +
                            'padding-top: 6px !important;' +
                            'padding-bottom: 2px !important;' +
                            '}' +
                            '.composer-box{' +
                            'padding-top: 6px !important;' +
                            'padding-bottom: 6px !important;' +
                            '}';
                        (document.head || document.documentElement).appendChild(style);
                    }
                } catch (error) {}
            })();
            """.trimIndent(),
            null,
        )
    }

    private fun showError(message: String) {
        progressBar.visibility = View.GONE
        errorMessageText.text = message
        errorPanel.visibility = View.VISIBLE
    }

    private fun hideError() {
        errorPanel.visibility = View.GONE
    }

    private fun updateCurrentUrlLabel(baseUrl: String) {
        currentUrlText.text = getString(R.string.current_backend, baseUrl)
    }

    private fun configuredEntryUrl(): String = "${getConfiguredBaseUrl()}/"

    private fun getConfiguredBaseUrl(): String {
        val stored = prefs.getString(PREF_BACKEND_URL, null).orEmpty()
        return normalizeBaseUrl(stored.ifBlank { BuildConfig.DEFAULT_BASE_URL })
    }

    private fun saveBackendUrl(url: String) {
        prefs.edit().putString(PREF_BACKEND_URL, normalizeBaseUrl(url)).apply()
        updateCurrentUrlLabel(getConfiguredBaseUrl())
    }

    private fun extractBaseUrl(rawUrl: String?): String? {
        if (rawUrl.isNullOrBlank()) {
            return null
        }
        return try {
            val uri = Uri.parse(rawUrl)
            val scheme = uri.scheme ?: return null
            val host = uri.host ?: return null
            val port = if (uri.port > 0) ":${uri.port}" else ""
            "$scheme://$host$port"
        } catch (_: Exception) {
            null
        }
    }

    private fun normalizeBaseUrl(raw: String): String {
        var value = raw.trim()
        if (value.isBlank()) {
            value = BuildConfig.DEFAULT_BASE_URL.trim()
        }
        if (!value.startsWith("http://", ignoreCase = true) &&
            !value.startsWith("https://", ignoreCase = true)
        ) {
            value = "http://$value"
        }
        while (value.endsWith("/")) {
            value = value.dropLast(1)
        }
        return value
    }

    private fun sanitizeAcceptTypes(rawAcceptTypes: Array<String>): List<String> {
        return rawAcceptTypes
            .flatMap { raw -> raw.split(",") }
            .map { type -> type.trim().lowercase(Locale.US) }
            .filter { type -> type.isNotBlank() && type != "*/*" }
            .distinct()
    }

    private fun resolvePickerMimeType(acceptTypes: List<String>): String {
        if (acceptTypes.isEmpty()) {
            return "*/*"
        }
        if (acceptTypes.all { it.startsWith("image/") }) {
            return "image/*"
        }
        if (acceptTypes.size == 1) {
            return acceptTypes.first()
        }
        return "*/*"
    }

    private fun shouldOfferCamera(acceptTypes: List<String>): Boolean {
        if (acceptTypes.isEmpty()) {
            return false
        }
        return acceptTypes.any { it == "image/*" || it.startsWith("image/") }
    }

    companion object {
        private const val PREFS_NAME = "openclaw_android_shell"
        private const val PREF_BACKEND_URL = "backend_url"
    }
}
