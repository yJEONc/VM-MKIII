console.log("MKIII UI Loaded");

let selectedGrade = null;
let selectedSchool = null;
let endData = [];

async function loadEndData() {
    const res = await fetch("/api/end_data");
    endData = await res.json();
}
loadEndData();

document.querySelectorAll("#grade-list li").forEach(li => {
    li.addEventListener("click", () => {
        selectedGrade = li.dataset.grade;
        loadSchools(selectedGrade);
    });
});

function loadSchools(grade){
    const schoolList = document.getElementById("school-list");
    schoolList.innerHTML = "";

    const schools = [...new Set(endData.filter(row => row[1] === grade).map(r => r[2]))];

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

async function loadUnits(){
    const res = await fetch("/api/preview_units", {
        method:"POST",
        headers:{ "Content-Type":"application/json" },
        body: JSON.stringify({ grade:selectedGrade, school:selectedSchool })
    });
    const units = await res.json();

    const area = document.getElementById("result-area");
    area.innerHTML = `<h2>${selectedSchool} | ${selectedGrade}학년</h2>`;

    const list = document.createElement("ul");
    units.forEach(u=>{
        const li=document.createElement("li");
        li.textContent = u.unit;
        list.appendChild(li);
    });
    area.appendChild(list);

    document.getElementById("btn-area").style.display="block";
}

document.getElementById("reload-btn").addEventListener("click", async ()=>{
    await fetch("/reload", { method:"POST" });
    await loadEndData();
    alert("시험범위 업데이트 완료!");
});

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
        body: JSON.stringify({ grade:selectedGrade, school:selectedSchool, units:[] })
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
