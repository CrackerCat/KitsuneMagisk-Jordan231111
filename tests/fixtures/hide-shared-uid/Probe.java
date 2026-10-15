package org.kitsune.pr12;

import android.app.Instrumentation;
import android.os.Bundle;
import android.os.Process;
import java.io.File;

// Two packages signed by the same disposable lab key use this instrumentation
// and one sharedUserId. Namespace selection remains process-specific; SU policy
// necessarily applies to their shared Linux UID.
public class Probe extends Instrumentation {
    @Override public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        start();
    }

    @Override public void onStart() {
        Bundle result = new Bundle();
        result.putString("uid", Integer.toString(Process.myUid()));
        result.putString("visible", Boolean.toString(new File("/system/etc/kitsune_pr12_marker").exists()));
        finish(-1, result);
    }
}
