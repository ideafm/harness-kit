export type Attachment={id:string;name:string;mime:string;size:number;sha256:string}
export type Execution={title:string;detail:string;next:string;attempt:number;started_at:number|null;elapsed_seconds:number|null;last_activity_at:number;retry_at:number|null;waiting:boolean}
export type Observation = {task_id:number;terminal_command:string;mode:"events";interactive:false}
export type Task = {attachments?:Attachment[];execution?:Execution; depends_on?:number[];dependency_wait?:{id:number;state:string}[];accepted_by?:string;manual_acceptance?:boolean;auto_apply_error?:string;stage_timings?:Record<string,number>; id:number; state:string; stage:string; updated:number; request:string; artifacts:string[]|Record<string,unknown>; question?:string; reason?:string; implementation_summary?:string; plan_version?:string|number; risk?:string; scope?:string; approval_reason?:string;observation?:Observation;preview?:{url:string;read_only?:boolean;mode?:ViewMode;version?:string|number;current?:boolean;persistent?:boolean};integration?:{source_commit:string;commit:string;branch:string};integration_error?:string;commit_error?:string;backend?:string }
export type Status = { auto_apply?:{enabled:boolean;confirmation_url:string};project:string|{name?:string;id?:string;backend?:string}; tasks:Task[]; worker:{running:boolean;starting?:boolean;pid?:number;managed_elsewhere?:boolean;task_id?:number;observation?:Observation} }
export type Control = { task:Task; revision:string; allowed_actions:string[]; pending_question_id?:string; plan:{version:string|number;digest:string}|null; result:{version:string|number;digest:string}|null; confirmation_urls:Record<string,string>;confirmation_widgets?:Record<string,string> }
export type Capabilities = { project_id:string; actions:string[]; events:boolean; apply:false; project_view?:boolean }
export type Session = { csrf_token?:string; confirmation_origin:string }
export type Operation = { operation_id:string; status:'pending'|'succeeded'|'failed';task_id:number;error?:{message:string} }
export type Artifact = {task:number;artifact:string;text:string;truncated:boolean}
export type Events = { items:{id:string;cursor:string;type:string;occurred_at:number;message:string}[];next_cursor:string;has_more:boolean }
export type Projects = {revision?:string;can_remove?:boolean;items:{id:string;name:string;backend?:string}[];default_project_id:string;connect_url:string}
export interface Transport { projectId?:string; get<T>(path:string,signal?:AbortSignal):Promise<T>; post<T>(path:string,body:unknown,key:string,csrf:string,revision?:string):Promise<T> }
export type ViewMode='checked'|'working'
export type ProjectView={revision:string|null;url:string|null;running:boolean;manually_stopped?:boolean;requested:{task:number;mode:ViewMode;revision:string|null}|null;active_task:number|null;mode:ViewMode|null;source_digest:string|null;current:boolean;building:boolean;message:string;error?:string|{code?:string;message:string}}
export type ProjectViewResponse={task_id:number|null;available:boolean;reason:string|null;revision:string|null;view:ProjectView|null;actions?:('select'|'refresh'|'stop')[]}
export type ViewOperation={operation_id:string;task_id:number|null;status:'succeeded'|'failed'|'pending';view?:ProjectView;error?:{code:string;message:string;retryable:boolean}}
