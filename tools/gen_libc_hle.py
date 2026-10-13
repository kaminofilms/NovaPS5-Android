import hashlib,base64,re,subprocess,sys
suf=bytes.fromhex('518D64A635DED8C1E6B039B1C3E55230')
def nid(n): return base64.b64encode(hashlib.sha1(n.encode()+suf).digest()[:8][::-1]).decode().rstrip('=').replace('/','-')
existing=set(re.findall(r'LIB_(?:FUNC|OBJECT)\("([^"]+)"',subprocess.run(['grep','-rho',r'LIB_\(FUNC\|OBJECT\)("[^"]*"','/home/claude/kyty-src/src/libs'],capture_output=True,text=True).stdout))
# name: (ret, params, body)  body uses a0,a1..; None body => forward ::name(a0..)
F={}
def fwd(name,ret,*params,host=None):
    F[name]=(ret,params,None,host or name)
def cus(name,ret,params,body):
    F[name]=(ret,params,body,None)
for n in ['acosf','expf','exp2f','log10f','log2f','tanf','tanhf']: fwd(n,'float','float')
for n in ['atan2f','fmodf','hypotf','powf','remainderf']: fwd(n,'float','float','float')
for n in ['exp','exp2','log','log10','log2','tanh']: fwd(n,'double','double')
fwd('pow','double','double','double')
fwd('frexp','double','double','int*'); fwd('frexpf','float','float','int*')
fwd('ldexp','double','double','int'); fwd('ldexpf','float','float','int')
fwd('llround','long long','double'); fwd('lroundf','long','float')
cus('__isfinite','int',['double'],'return std::isfinite(a0) ? 1 : 0;')
cus('__isfinitef','int',['float'],'return std::isfinite(a0) ? 1 : 0;')
cus('__isinff','int',['float'],'return std::isinf(a0) ? (a0 < 0 ? -1 : 1) : 0;')
cus('__isnormal','int',['double'],'return std::isnormal(a0) ? 1 : 0;')
cus('__isnormalf','int',['float'],'return std::isnormal(a0) ? 1 : 0;')
for n in ['isalnum','isprint','isspace','isxdigit','tolower','toupper']: fwd(n,'int','int')
for n in ['iswalnum','iswalpha','iswblank','iswcntrl','iswdigit','iswgraph','iswlower','iswprint','iswpunct','iswspace','iswupper','iswxdigit']: fwd(n,'int','wint_t')
for n in ['towlower','towupper']: fwd(n,'wint_t','wint_t')
fwd('wctype','wctype_t','const char*'); fwd('iswctype','int','wint_t','wctype_t'); fwd('btowc','wint_t','int'); fwd('wctob','int','wint_t')
fwd('memchr','const void*','const void*','int','size_t'); fwd('strcasecmp','int','const char*','const char*'); fwd('strcoll','int','const char*','const char*')
fwd('strcpy','char*','char*','const char*'); fwd('strcspn','size_t','const char*','const char*'); fwd('strspn','size_t','const char*','const char*')
fwd('strdup','char*','const char*'); fwd('strndup','char*','const char*','size_t'); fwd('strnlen','size_t','const char*','size_t')
fwd('strncat','char*','char*','const char*','size_t'); fwd('strpbrk','const char*','const char*','const char*'); fwd('strtok','char*','char*','const char*')
fwd('strxfrm','size_t','char*','const char*','size_t'); fwd('strerror','char*','int')
cus('strerror_r','int',['int','char*','size_t'],'if (a1 == nullptr || a2 == 0) return 34; std::snprintf(a1, a2, "%s", std::strerror(a0)); return 0;')
fwd('atof','double','const char*'); fwd('strtod','double','const char*','char**'); fwd('strtof','float','const char*','char**'); fwd('strtold','long double','const char*','char**')
fwd('strtoll','long long','const char*','char**','int'); fwd('strtoull','unsigned long long','const char*','char**','int')
fwd('wcslen','size_t','const wchar_t*'); fwd('wcscoll','int','const wchar_t*','const wchar_t*'); fwd('wcsxfrm','size_t','wchar_t*','const wchar_t*','size_t')
fwd('wcstod','double','const wchar_t*','wchar_t**'); fwd('wcstof','float','const wchar_t*','wchar_t**'); fwd('wcstold','long double','const wchar_t*','wchar_t**')
fwd('wcstol','long','const wchar_t*','wchar_t**','int'); fwd('wcstoll','long long','const wchar_t*','wchar_t**','int'); fwd('wcstoul','unsigned long','const wchar_t*','wchar_t**','int'); fwd('wcstoull','unsigned long long','const wchar_t*','wchar_t**','int')
fwd('wmemchr','const wchar_t*','const wchar_t*','wchar_t','size_t'); fwd('wmemcmp','int','const wchar_t*','const wchar_t*','size_t')
fwd('wcrtomb','size_t','char*','wchar_t','mbstate_t*'); fwd('mbrlen','size_t','const char*','size_t','mbstate_t*'); fwd('mbrtowc','size_t','wchar_t*','const char*','size_t','mbstate_t*')
fwd('mbsrtowcs','size_t','wchar_t*','const char**','size_t','mbstate_t*'); fwd('mbtowc','int','wchar_t*','const char*','size_t')
fwd('calloc','void*','size_t','size_t'); fwd('malloc','void*','size_t'); fwd('realloc','void*','void*','size_t'); fwd('free','void','void*')
fwd('posix_memalign','int','void**','size_t','size_t'); fwd('malloc_usable_size','size_t','void*')
fwd('bsearch','void*','const void*','const void*','size_t','size_t','NovaCompare'); fwd('qsort','void','void*','size_t','size_t','NovaCompare')
fwd('rand','int'); fwd('ctime','char*','const time_t*')
cus('getprogname','const char*',[],'return "eboot.bin";')
cus('setlocale','const char*',['int','const char*'],'return (a1 == nullptr || a1[0] == 0 || std::strcmp(a1, "C") == 0 || std::strcmp(a1, "POSIX") == 0) ? "C" : nullptr;')
cus('realpath','char*',['const char*','char*'],'if (a0 == nullptr) { *Posix::GetErrorAddr() = Posix::POSIX_EINVAL; return nullptr; } char* out = a1 != nullptr ? a1 : static_cast<char*>(std::malloc(1024)); std::snprintf(out, 1024, "%s", a0); return out; // guest paths are already absolute mount paths')
cus('_Unwind_Backtrace','int',['void*','void*'],'(void)a0; (void)a1; return 5; // _URC_END_OF_STACK')
cus('getenv','const char*',['const char*'],'(void)a0; return nullptr; // the guest environment is empty')
cus('unsetenv','int',['const char*'],'(void)a0; return 0;')
# stdio
cus('fopen','FILE*',['const char*','const char*'],'if (a0 == nullptr || a1 == nullptr) return nullptr; const auto real = LibKernel::FileSystem::GetRealFilename(a0); auto* f = std::fopen(real.empty() ? a0 : real.c_str(), a1); if (f == nullptr) *Posix::GetErrorAddr() = Posix::POSIX_ENOENT; return f;')
cus('fdopen','FILE*',['int','const char*'],'(void)a0; (void)a1; *Posix::GetErrorAddr() = Posix::POSIX_EINVAL; return nullptr;')
cus('fclose','int',['void*'],'if (GuestFd(a0) >= 0) return 0; return std::fclose(static_cast<FILE*>(a0));')
cus('fwrite','size_t',['const void*','size_t','size_t','void*'],'if (GuestFd(a3) >= 0) { const auto total = a1 * a2; return total == 0 ? 0 : static_cast<size_t>(std::max<int64_t>(0, GuestWrite(a3, a0, total))) / a1; } return std::fwrite(a0, a1, a2, static_cast<FILE*>(a3));')
cus('fread','size_t',['void*','size_t','size_t','void*'],'if (GuestFd(a3) >= 0) return 0; return std::fread(a0, a1, a2, static_cast<FILE*>(a3));')
cus('fputs','int',['const char*','void*'],'if (GuestFd(a1) >= 0) return GuestWrite(a1, a0, std::strlen(a0)) < 0 ? EOF : 0; return std::fputs(a0, static_cast<FILE*>(a1));')
cus('fputc','int',['int','void*'],'if (GuestFd(a1) >= 0) { const char c = static_cast<char>(a0); return GuestWrite(a1, &c, 1) == 1 ? (a0 & 0xff) : EOF; } return std::fputc(a0, static_cast<FILE*>(a1));')
cus('putchar','int',['int'],'const char c = static_cast<char>(a0); return LibKernel::FileSystem::KernelWrite(1, &c, 1) == 1 ? (a0 & 0xff) : EOF;')
cus('fgets','char*',['char*','int','void*'],'if (GuestFd(a2) >= 0) return nullptr; return std::fgets(a0, a1, static_cast<FILE*>(a2));')
cus('fgetc','int',['void*'],'if (GuestFd(a0) >= 0) return EOF; return std::fgetc(static_cast<FILE*>(a0));')
cus('getc','int',['void*'],'if (GuestFd(a0) >= 0) return EOF; return std::getc(static_cast<FILE*>(a0));')
cus('ungetc','int',['int','void*'],'if (GuestFd(a1) >= 0) return EOF; return std::ungetc(a0, static_cast<FILE*>(a1));')
cus('fseek','int',['void*','long','int'],'if (GuestFd(a0) >= 0) { *Posix::GetErrorAddr() = Posix::POSIX_ESPIPE; return -1; } return std::fseek(static_cast<FILE*>(a0), a1, a2);')
cus('fseeko','int',['void*','int64_t','int'],'if (GuestFd(a0) >= 0) { *Posix::GetErrorAddr() = Posix::POSIX_ESPIPE; return -1; } return ::fseeko(static_cast<FILE*>(a0), a1, a2);')
cus('ftell','long',['void*'],'if (GuestFd(a0) >= 0) { *Posix::GetErrorAddr() = Posix::POSIX_ESPIPE; return -1; } return std::ftell(static_cast<FILE*>(a0));')
cus('ftello','int64_t',['void*'],'if (GuestFd(a0) >= 0) { *Posix::GetErrorAddr() = Posix::POSIX_ESPIPE; return -1; } return ::ftello(static_cast<FILE*>(a0));')
cus('rewind','void',['void*'],'if (GuestFd(a0) < 0) std::rewind(static_cast<FILE*>(a0));')
cus('feof','int',['void*'],'if (GuestFd(a0) >= 0) return GuestFd(a0) == 0 ? 1 : 0; return std::feof(static_cast<FILE*>(a0));')
cus('ferror','int',['void*'],'if (GuestFd(a0) >= 0) return 0; return std::ferror(static_cast<FILE*>(a0));')
cus('fileno','int',['void*'],'const int fd = GuestFd(a0); return fd >= 0 ? fd : ::fileno(static_cast<FILE*>(a0));')
cus('setvbuf','int',['void*','char*','int','size_t'],'if (GuestFd(a0) >= 0) return 0; return std::setvbuf(static_cast<FILE*>(a0), a1, a2 == 0 ? _IOFBF : a2 == 1 ? _IOLBF : _IONBF, a3); // FreeBSD _IOFBF=0 _IOLBF=1 _IONBF=2')
cus('remove','int',['const char*'],'if (a0 == nullptr) return -1; const auto real = LibKernel::FileSystem::GetRealFilename(a0); return std::remove(real.empty() ? a0 : real.c_str());')
cus('fputwc','wint_t',['wchar_t','void*'],'char buffer[8]; std::mbstate_t state {}; const auto n = std::wcrtomb(buffer, a0, &state); if (n == static_cast<size_t>(-1)) return WEOF; if (GuestFd(a1) >= 0) return GuestWrite(a1, buffer, n) == static_cast<int64_t>(n) ? static_cast<wint_t>(a0) : WEOF; return std::fwrite(buffer, 1, n, static_cast<FILE*>(a1)) == n ? static_cast<wint_t>(a0) : WEOF;')
cus('fgetwc','wint_t',['void*'],'if (GuestFd(a0) >= 0) return WEOF; return std::fgetwc(static_cast<FILE*>(a0));')
cus('ungetwc','wint_t',['wint_t','void*'],'if (GuestFd(a1) >= 0) return WEOF; return std::ungetwc(a0, static_cast<FILE*>(a1));')
# va_list based
cus('vfprintf','int',['void*','const char*','NovaVaList'],'if (GuestFd(a0) >= 0) { char* text = nullptr; const int n = ::vasprintf(&text, a1, a2); if (n < 0) return -1; const auto written = GuestWrite(a0, text, static_cast<size_t>(n)); std::free(text); return written < 0 ? -1 : n; } return std::vfprintf(static_cast<FILE*>(a0), a1, a2);')
cus('vsnprintf','int',['char*','size_t','const char*','NovaVaList'],'return std::vsnprintf(a0, a1, a2, a3);')
cus('vsprintf','int',['char*','const char*','NovaVaList'],'return std::vsprintf(a0, a1, a2);')
cus('vasprintf','int',['char**','const char*','NovaVaList'],'return ::vasprintf(a0, a1, a2);')
cus('vsscanf','int',['const char*','const char*','NovaVaList'],'return std::vsscanf(a0, a1, a2);')
VARIADIC={'fprintf':('void*','vfprintf'),'sprintf':('char*','vsprintf'),'asprintf':('char**','vasprintf'),'sscanf':('const char*','vsscanf')}
out=[]
reg=[]
counter=[0]
for name,(ret,params,body,host) in F.items():
    n=nid(name)
    if n in existing: continue
    args=', '.join(f'{p} a{i}' for i,p in enumerate(params))
    call=', '.join(f'a{i}' for i in range(len(params)))
    if body is None:
        body=('' if ret=='void' else 'return ')+f'::{host}({call});'
    out.append(f'static KYTY_SYSV_ABI {ret} nova_{name.strip("_")}({args}) {{\n\t{body}\n}}\n')
    reg.append((n,name,out[-1].split('(')[0].split()[-1]))
for name,(first,vname) in VARIADIC.items():
    n=nid(name)
    if n in existing: continue
    vfn=[r[2] for r in reg if r[1]==vname][0]
    fn=f'nova_{name}_v'
    out.append(f'static KYTY_SYSV_ABI int {fn}({first} a0, const char* a1, ...) {{\n\tva_list ap;\n\tva_start(ap, a1);\n\tconst int r = {vfn}(a0, a1, ap);\n\tva_end(ap);\n\treturn r;\n}}\n')
    reg.append((n,name,fn))
for extra,obj in [('__isthreaded','&g_nova_isthreaded'),('__mb_cur_max','&g_nova_mb_cur_max'),('__mb_sb_limit','&g_nova_mb_sb_limit'),('_DefaultRuneLocale','&g_nova_rune_locale'),('_CurrentRuneLocale','&g_nova_current_rune_locale')]:
    n=nid(extra)
    if n not in existing: reg.append((n,extra,obj))
sj=[('_setjmp','::_setjmp'),('setjmp','::_setjmp'),('longjmp','::longjmp'),('_longjmp','::longjmp')]
code=[]
code.append('''// Nova: host-forwarded C library for titles that import firmware LibcInternal symbols
// directly (homebrew built with the open PS5 SDK). Retail games ship their own libc.prx.
// Linux only: guest and host share the SysV x86-64 ABI, so arguments, va_list and FILE*
// for host-opened files pass through unchanged. Guest standard streams map to Kyty's
// descriptors (pipes/dup2 included). wchar_t is the FreeBSD 32-bit type.
#if KYTY_PLATFORM == KYTY_PLATFORM_LINUX
namespace LibcNova {

LIB_VERSION("LibcInternal", 1, "LibcInternal", 1, 1);

using NovaCompare = int (*)(const void*, const void*);
using NovaVaList  = va_list;
static int g_nova_isthreaded = 1;
static int g_nova_mb_cur_max  = 1;   // "C" locale: single-byte
static int g_nova_mb_sb_limit = 256;

// FreeBSD amd64 _RuneLocale ("C" locale). Inline <ctype.h> macros in SDK-built titles index
// __runetype/__maplower/__mapupper directly through _CurrentRuneLocale.
struct NovaRuneRange { int32_t nranges; void* ranges; };
struct NovaRuneLocale {
	char magic[8]; char encoding[32]; void* sgetrune; void* sputrune; int32_t invalid_rune;
	uint64_t runetype[256]; int32_t maplower[256]; int32_t mapupper[256];
	NovaRuneRange runetype_ext, maplower_ext, mapupper_ext; void* variable; int32_t variable_len;
};
static_assert(offsetof(NovaRuneLocale, runetype) == 64 && offsetof(NovaRuneLocale, maplower) == 2112 &&
              offsetof(NovaRuneLocale, mapupper) == 3136 && offsetof(NovaRuneLocale, runetype_ext) == 4160);
static NovaRuneLocale MakeRuneLocale() {
	NovaRuneLocale r {};
	std::memcpy(r.magic, "RuneMagi", 8);
	std::memcpy(r.encoding, "NONE", 5);
	r.invalid_rune = 0xfffd;
	for (int c = 0; c < 256; c++) {
		uint64_t t = 0;
		if (c < 128) {
			if (std::isalpha(c)) t |= 0x100;
			if (std::iscntrl(c)) t |= 0x200;
			if (std::isdigit(c)) t |= 0x400 | static_cast<uint64_t>(c - '0');
			if (std::isgraph(c)) t |= 0x800;
			if (std::islower(c)) t |= 0x1000;
			if (std::ispunct(c)) t |= 0x2000;
			if (std::isspace(c)) t |= 0x4000;
			if (std::isupper(c)) t |= 0x8000;
			if (std::isxdigit(c)) { t |= 0x10000; if (!std::isdigit(c)) t |= static_cast<uint64_t>(std::tolower(c) - 'a' + 10); }
			if (c == ' ' || c == '\t') t |= 0x20000;
			if (std::isprint(c)) t |= 0x40000 | 0x40000000; // print, width 1
		}
		r.runetype[c] = t;
		r.maplower[c] = c < 128 ? std::tolower(c) : c;
		r.mapupper[c] = c < 128 ? std::toupper(c) : c;
	}
	return r;
}
static NovaRuneLocale  g_nova_rune_locale         = MakeRuneLocale();
static NovaRuneLocale* g_nova_current_rune_locale = &g_nova_rune_locale;

static int GuestFd(void* file) {
	if (file == LibcInternal::NovaGuestStream(0) || file == stdin) return 0;
	if (file == LibcInternal::NovaGuestStream(1) || file == stdout) return 1;
	if (file == LibcInternal::NovaGuestStream(2) || file == stderr) return 2;
	return -1;
}

static int64_t GuestWrite(void* file, const void* data, size_t size) {
	return LibKernel::FileSystem::KernelWrite(GuestFd(file), data, size);
}
''')
code+=out
code.append('LIB_DEFINE(InitLibcNova_1) {')
for n,name,fn in reg:
    kind='LIB_OBJECT' if fn.startswith('&') else 'LIB_FUNC'
    code.append(f'\t{kind}("{n}", {fn}); // {name}')
for name,host in sj:
    n=nid(name)
    if n not in existing: code.append(f'\tLIB_FUNC("{n}", {host}); // {name}: guest jmp_buf (96 bytes) holds glibc\'s 72-byte layout')
code.append('}\n\n} // namespace LibcNova\n#endif\n')
open(sys.argv[1],'w').write('\n'.join(code))
print(len(reg),'functions; skipped existing:',[k for k in F if nid(k) in existing])
