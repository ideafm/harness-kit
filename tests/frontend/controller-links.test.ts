import { it,expect } from 'vitest'
import { loopbackUrl,widgetUrl } from '@/lib/controller-links'
const origin='http://127.0.0.1:47832'
it('принимает только точный origin и путь встроенной формы',()=>{
 expect(widgetUrl(origin+'/confirm/embed?id=1',origin)).toBe(origin+'/confirm/embed?id=1')
 for(const url of [origin+'/confirm',origin+'/confirm/embed/','http://localhost:47832/confirm/embed','http://127.0.0.1:47833/confirm/embed',origin+'/confirm/embed#x','http://user@127.0.0.1:47832/confirm/embed','https://example.com/confirm/embed'])expect(widgetUrl(url,origin)).toBeUndefined()
 expect(widgetUrl(origin+'/confirm/embed',origin+'/')).toBeUndefined()
})
it('preview допускает только loopback http без credentials и fragment',()=>{
 expect(loopbackUrl('http://127.0.0.1:47832/preview/1')?.pathname).toBe('/preview/1')
 for(const url of ['javascript:alert(1)','https://example.com','http://127.0.0.1.example.com','http://user@localhost/','http://localhost/#token',undefined])expect(loopbackUrl(url)).toBeUndefined()
})
