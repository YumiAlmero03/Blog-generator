from app import create_app


def test_weekly_planner_page_renders_today_and_draggable_board():
    app = create_app()
    app.testing = True
    client = app.test_client()

    response = client.get("/weekly-planner")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Weekly Planner" in html
    assert "Tasks For Today" in html
    assert "data-task-list" in html
    assert "draggable = true" in html
    assert "dataset.editTask" in html
    assert "Double-click to edit" in html
    assert "dblclick" in html
    assert "Edit task" in html
    assert "weeklyPlannerTasks:v1" in html
