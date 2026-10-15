import groovy.json.JsonSlurper
import org.gradle.api.Plugin
import org.gradle.api.Project
import org.gradle.kotlin.dsl.provideDelegate
import java.io.File
import java.util.Properties
import java.util.Random

// Set non-zero value here to fix the random seed for reproducible builds
// CI builds are always reproducible
val RAND_SEED = if (System.getenv("CI") != null) 42 else 0
lateinit var RANDOM: Random
val ABI_SUPPORT_LIST = listOf("armeabi-v7a", "arm64-v8a", "x86", "x86_64", "riscv64")

val APP_ID get() = Config.identity["application_id"] as String
val PRODUCT_CHANNEL get() = Config.identity["channel"] as String
val PRODUCT_NAME get() = Config.identity["product_name"] as String
val UPSTREAM_BASE get() = Config.identity["upstream_commit"] as String

private val props = Properties()
private val supportAbis = setOf("armeabi-v7a", "x86", "arm64-v8a", "x86_64", "riscv64")
private val defaultAbis = setOf("armeabi-v7a", "x86", "arm64-v8a", "x86_64")

object Config {
    lateinit var identity: Map<*, *>
    lateinit var generatedDir: File
    lateinit var configFile: File

    fun buildInfo(variant: String) = File(generatedDir, "build-info-$variant.json").readText().trim()
    fun buildId(variant: String) = (JsonSlurper().parseText(buildInfo(variant)) as Map<*, *>)["build_id"] as String
    fun shellInfo(variant: String) = File(generatedDir, "build-info-$variant.sh").readText()
    operator fun get(key: String): String? {
        val v = props[key] as? String ?: return null
        return v.ifBlank { null }
    }

    fun contains(key: String) = get(key) != null

    val version: String get() = identity["version_name"] as String
    val versionCode: Int get() = (identity["app_version_code"] as Number).toInt()
    val compatVersionCode: Int get() = (identity["compat_version_code"] as Number).toInt()
    val protocolVersion: Int get() = (identity["protocol_version"] as Number).toInt()
    val stubVersion: String get() = get("magisk.stubVersion")!!
    val sourceCommit: String get() = identity["source_commit"] as String
    val sourceDirty: Boolean get() = identity["source_dirty"] as Boolean
    val abiList: Set<String> get() {
        val abiList = get("abiList") ?: return defaultAbis
        return abiList.split(Regex("\\s*,\\s*")).toSet() intersect supportAbis
    }
}

fun Project.rootFile(path: String): File {
    val file = File(path)
    return if (file.isAbsolute) file
    else File(rootProject.file(".."), path)
}

class MagiskPlugin : Plugin<Project> {
    override fun apply(project: Project) = project.applyPlugin()

    private fun Project.applyPlugin() {
        initRandom(rootProject.file("dict.txt"))
        props.clear()

        // Get gradle properties relevant to Magisk
        props.putAll(providers.gradlePropertiesPrefixedBy("magisk.").get())

        // Load config.prop
        val configPath = findProperty("configPath") as String?
        val configFile = rootFile(configPath ?: "config.prop")
        Config.configFile = configFile
        if (configFile.exists()) {
            configFile.inputStream().use {
                val config = Properties()
                config.load(it)
                props.putAll(config)
            }
        }

        // Commandline override
        findProperty("abiList")?.let { props.put("abiList", it) }

        check(listOf("version", "versionCode", "magisk.versionCode").none(Config::contains)) {
            "Set product identity in kitsune-build.json, not Gradle properties or config.prop"
        }
        val python = findProperty("pythonExecutable")?.toString()
            ?: if (System.getProperty("os.name").startsWith("Windows")) "python" else "python3"
        val generator = ProcessBuilder(python, "tools/build_info.py")
            .directory(rootFile(".")).redirectErrorStream(true).start()
        val output = generator.inputStream.bufferedReader().use { it.readText() }
        check(generator.waitFor() == 0) {
            "Cannot generate Kitsune build identity: $output"
        }
        Config.generatedDir = rootFile("native/out/generated")
        Config.identity = JsonSlurper().parse(File(Config.generatedDir, "build-info.json")) as Map<*, *>
        findProperty("expectedSourceCommit")?.toString()?.let {
            check(it == Config.sourceCommit) { "Git HEAD changed before Gradle accepted the build identity" }
        }
    }
}
