from app.domain.states import ProjectStatus, Stage, can_run, next_stage


def test_next_stage_follows_the_table():
    assert next_stage(ProjectStatus.SOURCE_APPROVED).stage is Stage.SCRIPT
    assert next_stage(ProjectStatus.SCENES_READY).stage is Stage.ANIMATE
    assert next_stage(ProjectStatus.MOTION_READY).stage is Stage.AUDIO
    assert next_stage(ProjectStatus.AUDIO_READY).stage is Stage.RENDER
    assert next_stage(ProjectStatus.QC_PASSED) is None  # waits for a human, not a stage
    assert next_stage(ProjectStatus.QC_APPROVED).stage is Stage.PUBLISH
    assert next_stage(ProjectStatus.UPLOADED) is None


def test_stages_can_rerun_but_not_skip_ahead():
    assert can_run(Stage.SCRIPT, ProjectStatus.RENDERED)          # re-run an earlier stage
    assert not can_run(Stage.RENDER, ProjectStatus.SCRIPT_READY)  # cannot jump ahead
    assert not can_run(Stage.PUBLISH, ProjectStatus.QC_PASSED)    # publish needs the approval
    assert can_run(Stage.PUBLISH, ProjectStatus.QC_APPROVED)
    assert not can_run(Stage.SCRIPT, ProjectStatus.CANCELLED)
