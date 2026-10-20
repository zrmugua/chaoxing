package cn.zrmug.chaoxing;

import android.content.*;
import android.os.*;
import android.os.Process;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

/** Anonymous pipes carry RPC data; Binder only transfers descriptors and the process ID. */
public final class AdapterPool {
    private static Context context;
    private static final Session[] slots = new Session[8];
    private static final Class<?>[] SERVICES = {AdapterServices.Slot0.class, AdapterServices.Slot1.class,
            AdapterServices.Slot2.class, AdapterServices.Slot3.class, AdapterServices.Slot4.class,
            AdapterServices.Slot5.class, AdapterServices.Slot6.class, AdapterServices.Slot7.class};

    public static void initialize(Context value) { context = value.getApplicationContext(); }

    public static Session open() throws Exception {
        Session session = null;
        synchronized (slots) {
            for (int index = 0; index < slots.length; index++) {
                if (slots[index] == null) { session = new Session(index); slots[index] = session; break; }
            }
        }
        if (session == null) throw new IOException("No adapter slot available");
        try { session.connect(); return session; }
        catch (Exception error) { session.close(); throw new IOException("Adapter process unavailable"); }
    }

    public static void closeAll() {
        Session[] current;
        synchronized (slots) { current = slots.clone(); }
        for (Session session : current) if (session != null) session.close();
    }

    public static final class Session implements ServiceConnection {
        private final int slot;
        private final BlockingQueue<String> messages = new LinkedBlockingQueue<>();
        private final CountDownLatch ready = new CountDownLatch(1), died = new CountDownLatch(1);
        private volatile IBinder binder;
        private volatile int pid;
        private volatile boolean closed;
        private boolean bound;
        private OutputStream requestOutput;
        private InputStream responseInput;
        private final Messenger replies = new Messenger(new Handler(Looper.getMainLooper(), message -> {
            pid = message.arg1; ready.countDown(); return true;
        }));

        private Session(int index) { slot = index; }

        private void connect() throws Exception {
            bound = context.bindService(new Intent(context, SERVICES[slot]), this, Context.BIND_AUTO_CREATE);
            if (!bound || !ready.await(30, TimeUnit.SECONDS) || pid <= 0 || closed)
                throw new IOException("Adapter startup timed out");
        }

        @Override public void onServiceConnected(ComponentName name, IBinder service) {
            if (closed) { context.unbindService(this); return; }
            binder = service;
            try {
                service.linkToDeath(this::processDied, 0);
                ParcelFileDescriptor[] input = ParcelFileDescriptor.createPipe();
                ParcelFileDescriptor[] output = ParcelFileDescriptor.createPipe();
                requestOutput = new ParcelFileDescriptor.AutoCloseOutputStream(input[1]);
                responseInput = new ParcelFileDescriptor.AutoCloseInputStream(output[0]);
                Message start = Message.obtain(null, 1);
                Bundle data = new Bundle(); data.putParcelable("input", input[0]); data.putParcelable("output", output[1]);
                start.setData(data); start.replyTo = replies;
                new Messenger(service).send(start);
                input[0].close(); output[1].close();
                Thread reader = new Thread(this::readMessages, "adapter-pipe"); reader.setDaemon(true); reader.start();
            } catch (Exception error) { pipeClosed(); ready.countDown(); }
        }

        private void readMessages() {
            try (Reader input = new InputStreamReader(responseInput, StandardCharsets.UTF_8)) {
                char[] buffer = new char[4096]; StringBuilder line = new StringBuilder(); int count;
                while ((count = input.read(buffer)) != -1) {
                    for (int i = 0; i < count; i++) {
                        if (buffer[i] == '\n') { messages.offer(line.toString()); line.setLength(0); }
                        else { line.append(buffer[i]); if (line.length() > 2_000_000) throw new IOException("RPC response exceeds limit"); }
                    }
                }
            } catch (IOException ignored) { }
            finally { pipeClosed(); }
        }

        private void pipeClosed() { messages.offer("{\"dead\":true}"); }
        private void processDied() { pipeClosed(); died.countDown(); }
        @Override public void onServiceDisconnected(ComponentName name) { processDied(); }
        @Override public void onBindingDied(ComponentName name) { processDied(); }
        @Override public void onNullBinding(ComponentName name) { pipeClosed(); ready.countDown(); }

        public synchronized void send(String request) throws IOException {
            if (closed || requestOutput == null || !isAlive()) throw new IOException("Adapter disconnected");
            byte[] data = (request + "\n").getBytes(StandardCharsets.UTF_8);
            if (data.length > 2_000_000) throw new IOException("RPC request exceeds limit");
            requestOutput.write(data); requestOutput.flush();
        }

        public String poll(int milliseconds) throws InterruptedException { return messages.poll(milliseconds, TimeUnit.MILLISECONDS); }
        public boolean isAlive() { return !closed && binder != null && binder.isBinderAlive() && died.getCount() != 0; }
        public boolean awaitDeath(int milliseconds) throws InterruptedException { return died.await(milliseconds, TimeUnit.MILLISECONDS); }
        public int processId() { return pid; }

        public void close() {
            if (closed) return;
            closed = true;
            if (pid > 0 && pid != Process.myPid() && binder != null && binder.isBinderAlive() && died.getCount() != 0)
                Process.killProcess(pid);
            try { if (requestOutput != null) requestOutput.close(); } catch (IOException ignored) { }
            try { if (responseInput != null) responseInput.close(); } catch (IOException ignored) { }
            try { if (bound) context.unbindService(this); } catch (IllegalArgumentException ignored) { }
            try {
                if (died.await(5, TimeUnit.SECONDS) || !bound || (binder != null && !binder.isBinderAlive())) {
                    synchronized (slots) { if (slots[slot] == this) slots[slot] = null; }
                }
            } catch (InterruptedException error) { Thread.currentThread().interrupt(); }
        }
    }
}
