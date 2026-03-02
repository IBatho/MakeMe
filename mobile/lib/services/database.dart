/// Local Drift database for offline caching.
///
/// Caches tasks and events locally so the app remains usable without
/// a network connection. The cache is refreshed whenever a successful
/// API response is received.
///
/// Generated files require running:
///   flutter pub run build_runner build --delete-conflicting-outputs
library;

import 'dart:io';

import 'package:drift/drift.dart';
import 'package:drift/native.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

part 'database.g.dart';

// ── Tables ────────────────────────────────────────────────────────────────────

/// Mirrors the Task API model for local caching.
class CachedTasks extends Table {
  TextColumn get id => text()();
  TextColumn get title => text()();
  TextColumn get description => text().nullable()();
  TextColumn get priority =>
      text().withDefault(const Constant('want'))(); // need|want|like
  IntColumn get totalDurationMinutes =>
      integer().withDefault(const Constant(60))();
  BoolColumn get isComplete => boolean().withDefault(const Constant(false))();
  TextColumn get deadline => text().nullable()(); // ISO 8601 date string
  DateTimeColumn get cachedAt =>
      dateTime().withDefault(currentDateAndTime)();

  @override
  Set<Column> get primaryKey => {id};
}

/// Mirrors the Event API model for local caching.
class CachedEvents extends Table {
  TextColumn get id => text()();
  TextColumn get title => text()();
  TextColumn get description => text().nullable()();
  TextColumn get location => text().nullable()();
  DateTimeColumn get startTime => dateTime()();
  DateTimeColumn get endTime => dateTime()();
  BoolColumn get isAllDay => boolean().withDefault(const Constant(false))();
  BoolColumn get isAgentCreated =>
      boolean().withDefault(const Constant(false))();
  DateTimeColumn get cachedAt =>
      dateTime().withDefault(currentDateAndTime)();

  @override
  Set<Column> get primaryKey => {id};
}

// ── DAOs ──────────────────────────────────────────────────────────────────────

@DriftAccessor(tables: [CachedTasks])
class TasksDao extends DatabaseAccessor<AppDatabase> with _$TasksDaoMixin {
  TasksDao(super.db);

  /// All cached tasks ordered by creation time desc (cached_at proxy).
  Future<List<CachedTask>> getAllTasks() =>
      (select(cachedTasks)..orderBy([(t) => OrderingTerm.desc(t.cachedAt)]))
          .get();

  Stream<List<CachedTask>> watchAllTasks() =>
      (select(cachedTasks)..orderBy([(t) => OrderingTerm.desc(t.cachedAt)]))
          .watch();

  Future<void> upsertTask(CachedTasksCompanion task) =>
      into(cachedTasks).insertOnConflictUpdate(task);

  Future<void> upsertTasks(List<CachedTasksCompanion> tasks) async {
    await batch((b) => b.insertAllOnConflictUpdate(cachedTasks, tasks));
  }

  Future<void> deleteTask(String id) =>
      (delete(cachedTasks)..where((t) => t.id.equals(id))).go();

  Future<void> clearAll() => delete(cachedTasks).go();
}

@DriftAccessor(tables: [CachedEvents])
class EventsDao extends DatabaseAccessor<AppDatabase> with _$EventsDaoMixin {
  EventsDao(super.db);

  Future<List<CachedEvent>> getEventsInRange(DateTime start, DateTime end) =>
      (select(cachedEvents)
            ..where(
              (e) =>
                  e.startTime.isBiggerOrEqualValue(start) &
                  e.endTime.isSmallerOrEqualValue(end),
            )
            ..orderBy([(e) => OrderingTerm(expression: e.startTime)]))
          .get();

  Stream<List<CachedEvent>> watchEventsInRange(DateTime start, DateTime end) =>
      (select(cachedEvents)
            ..where(
              (e) =>
                  e.startTime.isBiggerOrEqualValue(start) &
                  e.endTime.isSmallerOrEqualValue(end),
            )
            ..orderBy([(e) => OrderingTerm(expression: e.startTime)]))
          .watch();

  Future<void> upsertEvents(List<CachedEventsCompanion> events) async {
    await batch((b) => b.insertAllOnConflictUpdate(cachedEvents, events));
  }

  Future<void> deleteEvent(String id) =>
      (delete(cachedEvents)..where((e) => e.id.equals(id))).go();

  Future<void> clearAll() => delete(cachedEvents).go();
}

// ── Database ──────────────────────────────────────────────────────────────────

@DriftDatabase(tables: [CachedTasks, CachedEvents], daos: [TasksDao, EventsDao])
class AppDatabase extends _$AppDatabase {
  AppDatabase() : super(_openConnection());

  @override
  int get schemaVersion => 1;
}

LazyDatabase _openConnection() {
  return LazyDatabase(() async {
    final dir = await getApplicationDocumentsDirectory();
    final file = File(p.join(dir.path, 'makeme_cache.db'));
    return NativeDatabase.createInBackground(file);
  });
}

// ── Riverpod providers ────────────────────────────────────────────────────────

final appDatabaseProvider = Provider<AppDatabase>((ref) {
  final db = AppDatabase();
  ref.onDispose(db.close);
  return db;
});

final tasksDaoProvider = Provider<TasksDao>((ref) {
  return ref.watch(appDatabaseProvider).tasksDao;
});

final eventsDaoProvider = Provider<EventsDao>((ref) {
  return ref.watch(appDatabaseProvider).eventsDao;
});
