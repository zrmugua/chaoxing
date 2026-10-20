package cn.zrmug.chaoxing;

import java.net.*;
import java.util.*;

public final class LocalNetwork {
    public static List<String> addresses() {
        LinkedHashSet<String> result = new LinkedHashSet<>();
        try {
            for (NetworkInterface network : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                if (!network.isUp()) continue;
                for (InetAddress address : Collections.list(network.getInetAddresses())) {
                    if (address instanceof Inet4Address && address.isSiteLocalAddress() && !address.isLoopbackAddress())
                        result.add(address.getHostAddress());
                }
            }
        } catch (SocketException ignored) { }
        return new ArrayList<>(result);
    }
}
