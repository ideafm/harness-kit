export type Observation = {task_id:number;terminal_command:string;mode:"events";interactive:false}
export type Task = { id:number; state:string; stage:string; updated:number; request:string; artifacts:string[]|Record<string,unknown>; question?:string; reason?:string; implementation_summary?:string; plan_version?:string|number; risk?:string; scope?:string; approval_reason?:string;observation?:Observation;preview?:{url:string};integration?:{source_commit:string;commit:string;branch:string};integration_error?:string;commit_error?:string }
export type Status = { project:string|{name?:string;id?:string}; tasks:Task[]; worker:{running:boolean;starting?:boolean;pid?:number;managed_elsewhere?:boolean;task_id?:number;observation?:Observation} }
export type Control = { task:Task; revision:string; allowed_actions:string[]; pending_question_id?:string; plan:{version:string|number;digest:string}|null; result:{version:string|number;digest:string}|null; confirmation_urls:Record<string,string>;confirmation_widgets?:Record<string,string> }
export type Capabilities = { project_id:string; actions:string[]; events:boolean; apply:false }
export type Session = { csrf_token?:string; confirmation_origin:string }
export type Operation = { operation_id:string; status:'pending'|'succeeded'|'failed';task_id:number;error?:{message:string} }
export type Artifact = {task:number;artifact:string;text:string;truncated:boolean}
export type Events = { items:{id:string;cursor:string;type:string;occurred_at:number;message:string}[];next_cursor:string;has_more:boolean }
export type Projects = {items:{id:string;name:string}[];default_project_id:string;connect_url:string}
export interface Transport { projectId?:string; get<T>(path:string,signal?:AbortSignal):Promise<T>; post<T>(path:string,body:unknown,key:string,csrf:string,revision?:string):Promise<T> }
