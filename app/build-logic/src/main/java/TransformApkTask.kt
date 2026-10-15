import com.android.build.api.artifact.ArtifactTransformationRequest
import com.android.build.api.dsl.ApkSigningConfig
import com.android.builder.internal.packaging.IncrementalPackager
import com.android.ide.common.signing.KeystoreHelper
import com.android.tools.build.apkzlib.sign.SigningExtension
import com.android.tools.build.apkzlib.sign.SigningOptions
import com.android.tools.build.apkzlib.zfile.ZFiles
import com.android.tools.build.apkzlib.zip.ZFile
import com.android.tools.build.apkzlib.zip.ZFileOptions
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.ListProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.Internal
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.TaskAction
import java.io.File
import java.io.ByteArrayInputStream
import java.util.jar.JarFile

abstract class TransformApkTask : DefaultTask() {
    @get:InputFile
    abstract val updateTrust: RegularFileProperty
    @get:Input
    abstract val signingConfig: Property<ApkSigningConfig>

    @get:InputFiles
    abstract val apkFolder: DirectoryProperty

    @get:OutputDirectory
    abstract val outFolder: DirectoryProperty

    @get:Internal
    abstract val transformations: ListProperty<(ZFile) -> Unit>

    @get:Internal
    abstract val transformationRequest: Property<ArtifactTransformationRequest<TransformApkTask>>

    @TaskAction
    fun taskAction() = transformationRequest.get().submit(this) { artifact ->
        val inFile = File(artifact.outputFile)
        val outFile = outFolder.file(inFile.name).get().asFile

        val config = signingConfig.get()
        val info = KeystoreHelper.getCertificateInfo(
            config.storeType,
            config.storeFile,
            config.storePassword,
            config.keyPassword,
            config.keyAlias
        )

        val signingOptions = SigningOptions.builder()
            .setMinSdkVersion(0)
            .setV1SigningEnabled(true)
            .setV2SigningEnabled(true)
            .setKey(info.key)
            .setCertificates(info.certificate)
            .setValidation(SigningOptions.Validation.ASSUME_INVALID)
            .build()
        val options = ZFileOptions().apply {
            noTimestamps = true
            autoSortFiles = true
        }
        outFile.parentFile?.mkdirs()
        inFile.copyTo(outFile, overwrite = true)
        ZFiles.apk(outFile, options).use { zip ->
            SigningExtension(signingOptions).register(zip)
            zip.get(IncrementalPackager.APP_METADATA_ENTRY_PATH)?.delete()
            zip.get(IncrementalPackager.VERSION_CONTROL_INFO_ENTRY_PATH)?.delete()
            zip.get(JarFile.MANIFEST_NAME)?.delete()
            zip.get("assets/PublicSuffixDatabase.list")?.delete()
            zip.add("assets/manager-cert.der", ByteArrayInputStream(info.certificate.encoded))
            updateTrust.get().asFile.inputStream().use { zip.add("assets/update-trust.json", it) }
            transformations.get().forEach { transform -> transform(zip) }
        }

        outFile
    }
}
