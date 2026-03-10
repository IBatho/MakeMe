# Flutter wrapper
-keep class io.flutter.app.** { *; }
-keep class io.flutter.plugin.** { *; }
-keep class io.flutter.util.** { *; }
-keep class io.flutter.view.** { *; }
-keep class io.flutter.** { *; }
-keep class io.flutter.plugins.** { *; }

# Keep app classes
-keep class uk.ac.manchester.makeme.** { *; }

# Drift (SQLite ORM)
-keep class androidx.sqlite.** { *; }

# Riverpod / dart mirrors
-keepattributes *Annotation*
