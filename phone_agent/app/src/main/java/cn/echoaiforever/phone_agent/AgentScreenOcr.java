package cn.echoaiforever.phone_agent;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Rect;
import android.util.Base64;

import com.google.android.gms.tasks.Tasks;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.Text;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.TextRecognizer;
import com.google.mlkit.vision.text.chinese.ChineseTextRecognizerOptions;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.concurrent.TimeUnit;

final class AgentScreenOcr {
    private AgentScreenOcr() {
    }

    static JSONObject recognize() throws Exception {
        JSONObject shot = AgentScreenshotBridge.capture();
        if (shot == null) {
            return null;
        }
        String encoded = shot.optString("image_base64", "");
        if (encoded.isEmpty()) {
            return null;
        }
        byte[] bytes = Base64.decode(encoded, Base64.DEFAULT);
        Bitmap bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.length);
        if (bitmap == null) {
            return null;
        }
        TextRecognizer recognizer = TextRecognition.getClient(
                new ChineseTextRecognizerOptions.Builder().build()
        );
        try {
            InputImage image = InputImage.fromBitmap(bitmap, 0);
            Text result = Tasks.await(
                    recognizer.process(image),
                    6,
                    TimeUnit.SECONDS
            );
            JSONArray blocks = new JSONArray();
            for (Text.TextBlock block : result.getTextBlocks()) {
                Rect bounds = block.getBoundingBox();
                JSONObject item = new JSONObject();
                item.put("text", block.getText());
                if (bounds != null) {
                    item.put("left", bounds.left);
                    item.put("top", bounds.top);
                    item.put("right", bounds.right);
                    item.put("bottom", bounds.bottom);
                }
                blocks.put(item);
            }
            JSONObject data = new JSONObject();
            data.put("text", result.getText());
            data.put("blocks", blocks);
            data.put("width", bitmap.getWidth());
            data.put("height", bitmap.getHeight());
            return data;
        } finally {
            recognizer.close();
            bitmap.recycle();
        }
    }
}
