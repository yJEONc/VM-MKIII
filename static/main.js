let grade = null;
let school = null;

// 페이지 로드시 자동으로 학교 목록 표시
window.onload = function () {
    loadSchools();
    bindGradeClicks();
};

function bindGradeClicks() {
    document.querySelectorAll("[data-grade]").forEach(li => {
        li.onclick = () => {
            grade = li.dataset.grade;
            // active 클래스 처리
            document.querySelectorAll("[data-grade]").forEach(g => g.classList.remove("active"));
            li.classList.add("active");
            updateSelectedInfo();
            loadUnits();
        };
    });
}

// 학교 목록 로드
async function loadSchools() {
    const res = await fetch("/api/schools");
    const list = await res.json();

    const ul = document.getElementById("school-list");
    ul.innerHTML = "";

    list.forEach(s => {
        const li = document.createElement("li");
        li.textContent = s;
        li.classList.add("school-item");
        li.onclick = () => {
            school = s;
            // active 클래스 처리
            document.querySelectorAll("#school-list li").forEach(x => x.classList.remove("active"));
            li.classList.add("active");
            updateSelectedInfo();
            loadUnits();
        };
        ul.appendChild(li);
    });
}

// 선택 정보 표시
function updateSelectedInfo(units = null) {
    const box = document.getElementById("selected-info");
    if (!grade && !school) {
        box.textContent = "학년과 학교를 선택해주세요.";
        return;
    }

    let txt = "";
    if (grade) txt += `${grade}학년`;
    if (school) txt += ` / ${school}`;

    if (units && units.length > 0) {
        txt += ` / 단원: ${units.join(", ")}`;
    }

    box.textContent = txt;
}

// 단원 목록
async function loadUnits() {
    if (!grade || !school) return;

    const res = await fetch("/api/units", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ grade: grade, school: school })
    });

    const units = await res.json();
    const box = document.getElementById("units");
    box.innerHTML = "";

    // 선택 정보에 단원까지 표시
    updateSelectedInfo(units);

    // 단원별 버튼
    units.forEach(u => {
        const row = document.createElement("div");
        row.classList.add("unit-row");
        row.textContent = u + "  ";

        const b1 = document.createElement("button");
        b1.textContent = "서술형";
        b1.onclick = () => download(u, "서술형");

        const b2 = document.createElement("button");
        b2.textContent = "최다빈출";
        b2.onclick = () => download(u, "최다빈출");

        row.appendChild(b1);
        row.appendChild(b2);
        box.appendChild(row);
    });

    // 전체 병합 버튼
    const bottom = document.createElement("div");
    bottom.style.marginTop = "30px";

    const all1 = document.createElement("button");
    all1.textContent = "서술형 전체 합치기";
    all1.onclick = () => mergeAll("서술형");

    const all2 = document.createElement("button");
    all2.textContent = "최다빈출 전체 합치기";
    all2.onclick = () => mergeAll("최다빈출");

    bottom.appendChild(all1);
    bottom.appendChild(all2);

    box.appendChild(bottom);
}

// 단원 개별 다운로드
function download(unit, type) {
    fetch("/api/merge", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ grade: grade, unit: unit, type: type })
    }).then(async r => {
        if (!r.ok) {
            alert("파일 없음");
            return;
        }
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${grade}학년_${unit}_${type}.pdf`;
        a.click();
    });
}

// 전체 단원 병합 다운로드
function mergeAll(type) {
    fetch("/api/merge_all", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ grade: grade, school: school, type: type })
    }).then(async r => {
        if (!r.ok) {
            alert("전체 병합 파일이 없습니다.");
            return;
        }
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);

        const a = document.createElement("a");
        a.href = url;
        a.download = `${grade}학년_${school}_${type}_전체.pdf`;
        a.click();
    });
}
