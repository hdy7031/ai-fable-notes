"""Display-only curriculum order, independent of article metadata and progress."""

MAIN_STAGES = ("foundations", "training", "cnn", "sequence-models", "ocr")
BRANCH_STAGES = ("statistics", "probability", "probabilistic-learning")
APPLIED_STAGES = (
    "applied-workflow",
    "modern-vision",
    "llm-multimodal",
    "agent-systems",
)
MAIN_DESCRIPTION = "神经网络基础 → 训练机制 → CNN → 序列模型与 Transformer → OCR"
TRACK_STAGES = {"main": MAIN_STAGES, "applied": APPLIED_STAGES,
                "probability-statistics": BRANCH_STAGES}
TRACK_TITLES = {"main": "AI 基础主线", "applied": "AI 应用进阶",
                "probability-statistics": "概率与统计参考资料"}


def stage_track(stage_id):
    return next(track for track, stages in TRACK_STAGES.items() if stage_id in stages)


def ordered_stages(plan):
    ranks = {stage_id: index for index, stage_id in enumerate(MAIN_STAGES + APPLIED_STAGES + BRANCH_STAGES)}
    return sorted(plan["stages"], key=lambda stage: ranks.get(stage["id"], len(ranks)))


def navigation_lessons(plan, lessons):
    courses = [course for track in course_tracks(plan, lessons).values() for course in track]
    ranks = {course["id"]: index for index, course in enumerate(courses)}
    return sorted(lessons, key=lambda lesson: ranks[lesson["id"]])


def course_tracks(plan, lessons):
    """Include unpublished concepts so navigation cannot silently skip a gap."""
    tracks = {track: [] for track in TRACK_STAGES}
    for stage in ordered_stages(plan):
        actual = {lesson["id"]: lesson for lesson in lessons if lesson["category"] == stage["id"]}
        concepts = {concept["id"]: concept for concept in stage["concepts"]}
        concepts.update({concept_id: dict(concepts.get(concept_id, {}), **lesson)
                         for concept_id, lesson in actual.items()})
        titles = {concept["id"]: concept["title"] for concept in stage["concepts"]}
        track = stage_track(stage["id"])
        for concept in sorted(concepts.values(), key=lambda item: (item["order"], item["id"])):
            lesson = actual.get(concept["id"])
            tracks[track].append(dict(
                id=concept["id"], category=stage["id"],
                title=titles.get(concept["id"], concept["title"]),
                story=lesson["title"] if lesson else "正文尚未发布，可查看阶段计划。",
                prerequisites=concept.get("prerequisites", []),
                order=concept["order"], published=lesson is not None,
                url=lesson["url"] if lesson else f'generated/stages/{stage["id"]}/#concept-{concept["id"]}',
            ))
    return tracks


def course_neighbors(tracks, lesson_id):
    for courses in tracks.values():
        for index, course in enumerate(courses):
            if course["id"] == lesson_id:
                return (courses[index - 1] if index else None,
                        courses[index + 1] if index + 1 < len(courses) else None)
    return None, None
