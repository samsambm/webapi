package com.basketwatch.app;

import android.app.Activity;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/**
 * The whole app: one WebView over dashboard/index.html, which is copied into
 * assets at build time. The receipt data is baked into that page, so the
 * dashboard works with no network and no account.
 *
 * The one thing the page cannot do by itself is call Claude: a WebView page
 * loaded from file:// has no origin the Anthropic API will accept, so a direct
 * fetch dies on CORS. {@link Bridge#post} makes that request from Java instead,
 * where CORS does not apply, using the key the user typed into the app's own
 * settings. The key is passed in per call and never stored on this side.
 */
public class MainActivity extends Activity {

    private static final String API_URL = "https://api.anthropic.com/v1/messages";

    private WebView web;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);

        web = new WebView(this);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setSupportZoom(false);
        web.setWebViewClient(new WebViewClient());

        // Safe because the WebView only ever loads our own bundled asset — no
        // remote page can reach this object.
        web.addJavascriptInterface(new Bridge(), "BasketWatchNative");

        setContentView(web);

        if (state == null) {
            web.loadUrl("file:///android_asset/index.html");
        } else {
            web.restoreState(state);
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }

    /** Hands the page's JSON straight to the Anthropic API and calls it back. */
    private class Bridge {

        @JavascriptInterface
        public void post(final String apiKey, final String body, final String callbackId) {
            new Thread(new Runnable() {
                @Override
                public void run() {
                    int status = 0;
                    String result;
                    HttpURLConnection conn = null;
                    try {
                        conn = (HttpURLConnection) new URL(API_URL).openConnection();
                        conn.setRequestMethod("POST");
                        conn.setRequestProperty("content-type", "application/json");
                        conn.setRequestProperty("x-api-key", apiKey);
                        conn.setRequestProperty("anthropic-version", "2023-06-01");
                        conn.setDoOutput(true);
                        conn.setConnectTimeout(30000);
                        // Reading a receipt can take a couple of minutes.
                        conn.setReadTimeout(240000);

                        OutputStream out = conn.getOutputStream();
                        try {
                            out.write(body.getBytes(StandardCharsets.UTF_8));
                        } finally {
                            out.close();
                        }

                        status = conn.getResponseCode();
                        InputStream in = status >= 400 ? conn.getErrorStream() : conn.getInputStream();
                        result = readAll(in);
                    } catch (Exception e) {
                        JSONObject error = new JSONObject();
                        try {
                            JSONObject inner = new JSONObject();
                            inner.put("type", "network");
                            inner.put("message", String.valueOf(e.getMessage()));
                            error.put("error", inner);
                        } catch (Exception ignored) { /* the shape below is fixed */ }
                        result = error.toString();
                    } finally {
                        if (conn != null) conn.disconnect();
                    }
                    deliver(callbackId, status, result);
                }
            }).start();
        }

        private String readAll(InputStream in) throws Exception {
            if (in == null) return "";
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            byte[] chunk = new byte[8192];
            int read;
            try {
                while ((read = in.read(chunk)) != -1) buffer.write(chunk, 0, read);
            } finally {
                in.close();
            }
            return new String(buffer.toByteArray(), StandardCharsets.UTF_8);
        }

        private void deliver(final String callbackId, final int status, final String bodyText) {
            final String js = "window.__nativePost(" + JSONObject.quote(callbackId) + ","
                    + status + "," + JSONObject.quote(bodyText) + ")";
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    web.evaluateJavascript(js, null);
                }
            });
        }
    }
}
