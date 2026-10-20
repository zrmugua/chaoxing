package cn.zrmug.chaoxing;

import android.app.Service;
import android.content.Intent;
import android.os.*;
import mobile.Mobile;

public final class AdapterServices {
    public abstract static class Base extends Service {
        private HandlerThread thread;
        private Messenger messenger;
        private boolean started;

        @Override public void onCreate() {
            super.onCreate();
            thread = new HandlerThread("core-runtime"); thread.start();
            messenger = new Messenger(new Handler(thread.getLooper(), message -> {
                if (message.what != 1 || started) return true;
                started = true;
                try {
                    ParcelFileDescriptor incoming = message.getData().getParcelable("input");
                    ParcelFileDescriptor outgoing = message.getData().getParcelable("output");
                    Message ready = Message.obtain(null, 2); ready.arg1 = android.os.Process.myPid();
                    message.replyTo.send(ready);
                    Mobile.serve(incoming.detachFd(), outgoing.detachFd());
                } catch (Exception ignored) { }
                finally { android.os.Process.killProcess(android.os.Process.myPid()); }
                return true;
            }));
        }
        @Override public IBinder onBind(Intent intent) { return messenger.getBinder(); }
        @Override public boolean onUnbind(Intent intent) {
            android.os.Process.killProcess(android.os.Process.myPid()); return false;
        }
    }
    public static final class Slot0 extends Base { }
    public static final class Slot1 extends Base { }
    public static final class Slot2 extends Base { }
    public static final class Slot3 extends Base { }
    public static final class Slot4 extends Base { }
    public static final class Slot5 extends Base { }
    public static final class Slot6 extends Base { }
    public static final class Slot7 extends Base { }
}
