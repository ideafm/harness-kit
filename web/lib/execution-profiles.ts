export const executionProfiles:Record<string,string>={
 'auto-balanced':'Авто — сбалансированный',
 thorough:'Усиленный план и ревью',
 manual:'Один агент — настройки проекта'
}
export function profileDescription(profile:string,backend:string){
 if(profile==='manual')return 'Все этапы выполняет выбранный агент с настройками проекта. Проверки и независимое ревью сохраняются.'
 const implementation=backend==='gemini'?'Gemini':'Sol'
 return profile==='thorough'?`План: Astra → реализация: ${implementation} → ревью: Astra. Проверки обязательны.`:`План: Sol; при сложности или риске — Astra → реализация: ${implementation} → независимое ревью: Sol или Astra. При повторных неудачах модель повышается.`
}
