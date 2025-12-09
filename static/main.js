let grade = null;
let gradeSchools = [];          // end 시트에 해당 학년으로 존재하는 학교들
let selectedSchools = new Set(); // 사용자가 선택한 학교들
let allSchools = [];            // 전체 학교 목록

window.onload = function () {
    loadSchools();
    bindGradeClicks();
};

function bindGradeClicks() {
    document.querySelectorAll("[data-grade]").forEach(li => {
        li.onclick = async () => {
            grade = li.dataset.grade;

            // 학년 active 표시
            document.querySelectorAll("[data-grade]").forEach(g => g.classList.remove("active"));
            li.classList.add("active");

            // 학년이 바뀌면 선택된 학교는 유지할지? -> 유지하되 색상/단원 다시 계산
            await loadGradeSchools();
            updateSelectedInfo();
            updateSchoolStyles();
            renderUnits();
        };
    });
}

// 전체 학교 목록 로딩
async function loadSchools() {
    const res = await fetch("/api/schools");
    allSchools = await res.json();

    const ul = document.getElementById("school-list");
    ul.innerHTML = "";

    allSchools.forEach(s => {
        const li = document.createElement("li");
        li.textContent = s;
        li.dataset.school = s;
        li.classList.add("school-item");
        li.onclick = () => toggleSchoolSelection(s);
        ul.appendChild(li);
    });
}

// 특정 학년에 대해 end 시트에 존재하는 학교 목록 로딩
async function loadGradeSchools() {
    if (!grade) {
        gradeSchools = [];
        return;
    }
    const res = await fetch("/api/grade_schools", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ grade: grade })
    });
    gradeSchools = await res.json();
}

// 학교 선택 토글
function toggleSchoolSelection(schoolName) {
    if (!grade) {
        alert("먼저 학년을 선택하세요.");
        return;
    }
    if (selectedSchools.has(schoolName)) {
        selectedSchools.delete(schoolName);
    } else {
        selectedSchools.add(schoolName);
    }
    updateSelectedInfo();
    updateSchoolStyles();
    renderUnits();
}

// 상단 선택 정보 업데이트
function updateSelectedInfo() {
    const box = document.getElementById("selected-info");
    if (!grade && selectedSchools.size === 0) {
        box.textContent = "학년과 학교를 선택해주세요.";
        return;
    }

    let parts = [];
    if (grade) parts.push(grade + "학년");
    if (selectedSchools.size > 0) {
        parts.push("학교: " + Array.from(selectedSchools).join(", "));
    }

    box.textContent = parts.join(" / ");
}

// 학교 리스트 색상/스타일 업데이트
function updateSchoolStyles() {
    const lis = document.querySelectorAll("#school-list li");
    lis.forEach(li => {
        const name = li.dataset.school;
        li.classList.remove("has-end", "selected");

        // end 시트에 해당 학년+학교가 있으면 파랑 계열 텍스트
        if (grade && gradeSchools.includes(name)) {
            li.classList.add("has-end");
        }

        // 사용자가 선택한 학교는 녹색 (선택 색상 우선)
        if (selectedSchools.has(name)) {
            li.classList.add("selected");
        }
    });
}

// 학교별 단원 카드 렌더링
async function renderUnits() {
    const container = document.getElementById("unit-columns");
    container.innerHTML = "";

    if (!grade || selectedSchools.size === 0) return;

    const schools = Array.from(selectedSchools);

    for (const sch of schools) {
        const card = await buildSchoolCard(grade, sch);
        container.appendChild(card);
    }
}

// 한 학교 카드 생성
async function buildSchoolCard(gradeVal, schoolName) {
    // 단원 코드 가져오기
    const resCodes = await fetch("/api/units", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ grade: gradeVal, school: schoolName })
    });
    const codes = await resCodes.json();

    // 단원명이 필요하면 매핑 가져오기
    let mapping = {};
    if (Array.isArray(codes) && codes.length > 0) {
        const resMap = await fetch("/api/unit_names", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ grade: gradeVal, codes: codes })
        });
        mapping = await resMap.json();
    }

    const card = document.createElement("div");
    card.classList.add("school-card");

    const header = document.createElement("div");
    header.classList.add("school-card-header");
    header.textContent = gradeVal + "학년 " + schoolName;
    card.appendChild(header);

    const body = document.createElement("div");
    body.classList.add("school-card-body");

    if (!codes || codes.length === 0) {
        const p = document.createElement("p");
        p.textContent = "등록된 단원이 없습니다.";
        body.appendChild(p);
    } else {
        const ul = document.createElement("ul");
        codes.forEach(code => {
            const li = document.createElement("li");
            const name = mapping[code] || "";
            li.textContent = name ? `${code} ${name}` : code;
            ul.appendChild(li);
        });
        body.appendChild(ul);
    }
    card.appendChild(body);

    const footer = document.createElement("div");
    footer.classList.add("school-card-footer");

    const b1 = document.createElement("button");
    b1.textContent = "서술형 전체 합치기";
    b1.onclick = () => mergeAll(gradeVal, schoolName, "서술형");

    const b2 = document.createElement("button");
    b2.textContent = "최다빈출 전체 합치기";
    b2.onclick = () => mergeAll(gradeVal, schoolName, "최다빈출");

    footer.appendChild(b1);
    footer.appendChild(b2);

    card.appendChild(footer);

    return card;
}

// 학교별 전체 단원 병합 다운로드
function mergeAll(gradeVal, schoolName, type) {
    fetch("/api/merge_all", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ grade: gradeVal, school: schoolName, type: type })
    }).then(async r => {
        if (!r.ok) {
            alert("병합할 파일이 없습니다.");
            return;
        }
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);

        const a = document.createElement("a");
        a.href = url;
        a.download = `${gradeVal}학년_${schoolName}_${type}_전체.pdf`;
        a.click();
    });
}
