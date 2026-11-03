package cn.echoaiforever.phone_agent;

import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.PixelFormat;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.os.Handler;
import android.os.HandlerThread;
import android.util.Base64;
import android.util.DisplayMetrics;
import android.view.WindowManager;

import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;

final class AgentScreenCapture {
    private final Context context;
    private MediaProjection projection;
    private ImageReader imageReader;
    private VirtualDisplay virtualDisplay;
    private HandlerThread thread;
    private Handler handler;
    private int width;
    private int height;

    AgentScreenCapture(Context context) {
        this.context = context;
    }

    boolean isReady() {
        return projection != null && imageReader != null;
    }

    boolean start(int resultCode, Intent data) {
        stop();
        MediaProjectionManager manager = (MediaProjectionManager) context.getSystemService(
                Context.MEDIA_PROJECTION_SERVICE
        );
        projection = manager.getMediaProjection(resultCode, data);
        if (projection == null) {
            return false;
        }
        WindowManager windowManager = (WindowManager) context.getSystemService(
                Context.WINDOW_SERVICE
        );
        DisplayMetrics metrics = new DisplayMetrics();
        windowManager.getDefaultDisplay().getRealMetrics(metrics);
        width = metrics.widthPixels;
        height = metrics.heightPixels;
        imageReader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2);
        thread = new HandlerThread("echo-screen-capture");
        thread.start();
        handler = new Handler(thread.getLooper());
        virtualDisplay = projection.createVirtualDisplay(
                "echo-screen",
                width,
                height,
                metrics.densityDpi,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                imageReader.getSurface(),
                null,
                handler
        );
        return virtualDisplay != null;
    }

    String captureBase64() {
        if (!isReady()) {
            return "";
        }
        Image image = null;
        for (int attempt = 0; attempt < 10 && image == null; attempt++) {
            image = imageReader.acquireLatestImage();
            if (image == null) {
                try {
                    Thread.sleep(50);
                } catch (InterruptedException exc) {
                    Thread.currentThread().interrupt();
                    return "";
                }
            }
        }
        if (image == null) {
            return "";
        }
        try {
            Image.Plane plane = image.getPlanes()[0];
            ByteBuffer buffer = plane.getBuffer();
            int pixelStride = plane.getPixelStride();
            int rowStride = plane.getRowStride();
            int rowPadding = rowStride - pixelStride * width;
            int paddedWidth = width + rowPadding / pixelStride;
            Bitmap padded = Bitmap.createBitmap(
                    paddedWidth,
                    height,
                    Bitmap.Config.ARGB_8888
            );
            padded.copyPixelsFromBuffer(buffer);
            Bitmap cropped = Bitmap.createBitmap(padded, 0, 0, width, height);
            int targetWidth = Math.min(720, width);
            int targetHeight = Math.round(height * (targetWidth / (float) width));
            Bitmap scaled = Bitmap.createScaledBitmap(
                    cropped,
                    targetWidth,
                    targetHeight,
                    true
            );
            ByteArrayOutputStream stream = new ByteArrayOutputStream();
            scaled.compress(Bitmap.CompressFormat.JPEG, 65, stream);
            padded.recycle();
            if (cropped != scaled) {
                cropped.recycle();
            }
            scaled.recycle();
            return Base64.encodeToString(stream.toByteArray(), Base64.NO_WRAP);
        } finally {
            image.close();
        }
    }

    void stop() {
        if (virtualDisplay != null) {
            virtualDisplay.release();
            virtualDisplay = null;
        }
        if (imageReader != null) {
            imageReader.close();
            imageReader = null;
        }
        if (projection != null) {
            projection.stop();
            projection = null;
        }
        if (thread != null) {
            thread.quitSafely();
            thread = null;
            handler = null;
        }
    }
}
