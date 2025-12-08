let grade=null, school=null;

document.querySelectorAll("[data-grade]").forEach(li=>{
    li.onclick=()=>{
        grade=li.dataset.grade;
        loadSchools();
    };
});

async function loadSchools(){
    const res=await fetch("/api/schools");
    const list=await res.json();
    const ul=document.getElementById("school-list");
    ul.innerHTML="";
    list.forEach(s=>{
        const li=document.createElement("li");
        li.textContent=s;
        li.onclick=()=>{ school=s; loadUnits(); };
        ul.appendChild(li);
    });
}

async function loadUnits(){
    const res=await fetch("/api/units",{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({grade:grade,school:school})
    });
    const units=await res.json();
    const box=document.getElementById("units");
    box.innerHTML="";
    units.forEach(u=>{
        const row=document.createElement("div");
        row.textContent=u+"  ";
        const b1=document.createElement("button");
        b1.textContent="서술형";
        b1.onclick=()=>download(u,"서술형");
        const b2=document.createElement("button");
        b2.textContent="최다빈출";
        b2.onclick=()=>download(u,"최다빈출");
        row.appendChild(b1); row.appendChild(b2);
        box.appendChild(row);
    });
}

function download(unit,type){
    fetch("/api/merge",{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({grade:grade,unit:unit,type:type})
    }).then(async r=>{
        if(!r.ok){ alert("파일 없음"); return;}
        const blob=await r.blob();
        const url=URL.createObjectURL(blob);
        const a=document.createElement("a");
        a.href=url;
        a.download=`${grade}학년_${unit}_${type}.pdf`;
        a.click();
    });
}
