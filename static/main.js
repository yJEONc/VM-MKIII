console.log("MKIII UI Loaded");

let selectedGrade = null;
let selectedSchool = null;
let endData = [];

// =====================
// END 데이터 로드
// =====================
async function loadEndData() {
    const res = await fetch("/api/end_data");
    endData = await res.json();
}
loadEndData();

// =====================
// 학년 선택 이벤트
// =====================
document.querySelectorAll("#grade-list li").forEach(li => {
    li.addEventListener("click", () => {
        selectedGrade = parseInt(li.dataset.grade);
        loadSchools(selectedGrade);
    });
});

// =====================
// 학교 목록 생성
// =====================
function loadSchools(grade){
    const schoolList = document.getElementById("school-list");
    schoolList.innerHTML = "";

    // 백엔드 구조에 맞게 수정
    const schools = [...new Set(
        endData
            .filter(row => row.grade === grade)
            .map(row => row.school)
    )];

    schools.forEach(school => {
        const li = document.createElement("li");
        li.textContent = school;
        li.addEventListener("click", () => {
            selectedSchool = school;
            loadUnits();
        });
        schoolList.appendChild(li);
    });
}

// =====================
// 단원 미리보기
// =====================
async function loadUnits(){
    const res = await fetch("/api/preview_units", {
        method:"POST",
        headers:{ "Content-Type":"application/json" },
        body: JSON.stringify({ grade:selectedGrade, school:selectedSchool })
    });
    
    const data = await res.json();
    const units = data.units;

    const area = document.getElementById("result-area");
    area.innerHTML = `<h2>${selectedSchool} | ${selectedGrade}학년</h2>`;

    const list = document.createElement("ul");
    units.forEach(u => {
        const li=document.createElement("li");
        li.textContent = `${u.code} - ${u.title}`;
        list.appendChild(li);
    });
    area.appendChild(list);

    document.getElementById("btn-area").style.display="block";
}

// =====================
// 시험범위 업데이트
// =====================
document.getElementById("reload-btn").addEventListener("click", async ()=>{
    await fetch("/reload", { method:"POST" });
    await loadEndData();
    alert("시험범위 업데이트 완료!");
});

// =====================
// PDF 생성 버튼
// =====================
document.getElementById("btn-descriptive").addEventListener("click", ()=>{
    mergePDF("서술형");
});
document.getElementById("btn-chodata").addEventListener("click", ()=>{
    mergePDF("최다빈출");
});

async function mergePDF(type){
    const res = await fetch(`/merge/${type}`, {
        method:"POST",
        headers:{ "Content-Type":"application/json" },
        body: JSON.stringify({ grade:selectedGrade, school:selectedSchool })
    });
    if(res.ok){
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${selectedSchool}_${selectedGrade}학년_${type}.pdf`;
        a.click();
    } else {
        alert("자료 없음 또는 오류 발생");
    }
}
