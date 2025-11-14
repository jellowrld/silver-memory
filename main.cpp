// main.cpp
// Fullbright GPU Overlay in C++
// - DirectX11 + DXGI Desktop Duplication
// - Dear ImGui control panel
// - Overlay mode + System Gamma mode
// - Multi-monitor selection with names
// - Per-game profiles (auto switching)
// - Monitor brightness capture/restore via DXVA2 (DDC/CI where supported)
// - Effects: Normal, Night Vision, Thermal, HDR-ish
// - Performance mode: Standard vs Ultra (lighter shader path)
// ---------------------------------------------------------------------------
// REQUIREMENTS:
//   - Dear ImGui core + imgui_impl_win32.cpp + imgui_impl_dx11.cpp
//   - Link: d3d11.lib, dxgi.lib, d3dcompiler.lib, dxva2.lib, psapi.lib
// ---------------------------------------------------------------------------

#include <windows.h>
#include <d3d11.h>
#include <dxgi1_2.h>
#include <d3dcompiler.h>
#include <dxva2.h>
#include <psapi.h>
#include <wrl/client.h>

#include <string>
#include <vector>
#include <map>
#include <chrono>
#include <fstream>
#include <sstream>
#include <mutex>

#include "imgui.h"
#include "imgui_impl_win32.h"
#include "imgui_impl_dx11.h"

#pragma comment(lib, "d3d11.lib")
#pragma comment(lib, "dxgi.lib")
#pragma comment(lib, "d3dcompiler.lib")
#pragma comment(lib, "dxva2.lib")
#pragma comment(lib, "psapi.lib")

using Microsoft::WRL::ComPtr;

// Forward ImGui Win32 handler
extern IMGUI_IMPL_API LRESULT ImGui_ImplWin32_WndProcHandler(HWND, UINT, WPARAM, LPARAM);

// --------------------------------------------------
// Global DX / window
// --------------------------------------------------
HWND                        g_hWnd          = nullptr;
ComPtr<ID3D11Device>        g_device;
ComPtr<ID3D11DeviceContext> g_context;
ComPtr<IDXGISwapChain>      g_swapChain;
ComPtr<ID3D11RenderTargetView> g_rtv;

// Desktop duplication
ComPtr<IDXGIOutputDuplication> g_duplication;
ComPtr<ID3D11Texture2D>        g_dupTex;
ComPtr<ID3D11ShaderResourceView> g_dupSRV;

// Shaders / pipeline
ComPtr<ID3D11VertexShader>   g_vs;
ComPtr<ID3D11PixelShader>    g_ps;
ComPtr<ID3D11InputLayout>    g_layout;
ComPtr<ID3D11SamplerState>   g_sampler;
ComPtr<ID3D11Buffer>         g_vb;
ComPtr<ID3D11Buffer>         g_cb;

// Gamma ramp backup
struct GammaRamp {
    WORD Red[256];
    WORD Green[256];
    WORD Blue[256];
};
GammaRamp g_defaultGamma = {};
bool      g_haveDefaultGamma = false;

// Multi-monitor info
struct MonitorInfo {
    int                 index;
    std::wstring        deviceName;   // from DXGI_OUTPUT_DESC.DeviceName
    HMONITOR            hMonitor;
    bool                hasBrightness = false;
    DWORD               minBright = 0;
    DWORD               maxBright = 0;
    DWORD               defaultBright = 0;
};
std::vector<MonitorInfo> g_monitors;
int                      g_currentMonitorIndex = 0;

// App modes / effects
enum class Mode      { Overlay = 0, SystemGamma = 1 };
enum class Effect    { Normal = 0, NightVision = 1, Thermal = 2, HDRish = 3 };
enum class PerfMode  { Standard = 0, Ultra = 1 };

// Current settings (editable via ImGui)
struct Settings {
    float    brightness = 1.8f;
    float    gamma      = 0.6f;
    float    opacity    = 1.0f;  // reserved if you want blending later
    Mode     mode       = Mode::Overlay;
    Effect   effect     = Effect::Normal;
    PerfMode perf       = PerfMode::Standard;
};
Settings g_settings;

// Profiles (by key: "global" or "game:exeName")
struct Profile {
    float    brightness;
    float    gamma;
    float    opacity;
    Mode     mode;
    Effect   effect;
    PerfMode perf;
    int      monitorIndex;
};
std::map<std::string, Profile> g_profiles;
std::string                    g_currentProfileKey = "global";
std::string                    g_currentExeName;
std::mutex                     g_profileMutex;

// Constant buffer
struct CBParams {
    float Brightness;
    float Gamma;
    float EffectType;   // 0=normal,1=night,2=thermal,3=HDRish
    float PerfType;     // 0=standard,1=ultra
};

// Fullscreen quad vertex
struct FSVertex {
    float pos[3];
    float uv[2];
};

bool g_running = true;

// --------------------------------------------------
// Win32 / ImGui boilerplate
// --------------------------------------------------
LRESULT CALLBACK WndProc(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    if (ImGui_ImplWin32_WndProcHandler(hWnd, msg, wParam, lParam))
        return true;

    switch (msg) {
        case WM_DESTROY:
            g_running = false;
            PostQuitMessage(0);
            return 0;
        default:
            return DefWindowProc(hWnd, msg, wParam, lParam);
    }
}

bool InitWindow(HINSTANCE hInst) {
    WNDCLASSEX wc = {};
    wc.cbSize        = sizeof(WNDCLASSEX);
    wc.style         = CS_HREDRAW | CS_VREDRAW;
    wc.lpfnWndProc   = WndProc;
    wc.hInstance     = hInst;
    wc.hCursor       = LoadCursor(nullptr, IDC_ARROW);
    wc.lpszClassName = L"FullBrightOverlayClass";

    if (!RegisterClassEx(&wc)) return false;

    RECT rc;
    GetClientRect(GetDesktopWindow(), &rc);
    int width  = rc.right - rc.left;
    int height = rc.bottom - rc.top;

    g_hWnd = CreateWindowEx(
        WS_EX_TOPMOST | WS_EX_LAYERED,
        wc.lpszClassName,
        L"FullBright Overlay",
        WS_POPUP,
        0, 0, width, height,
        nullptr, nullptr, hInst, nullptr
    );
    if (!g_hWnd) return false;

    // Click-through
    LONG ex = GetWindowLong(g_hWnd, GWL_EXSTYLE);
    ex |= WS_EX_TRANSPARENT;
    SetWindowLong(g_hWnd, GWL_EXSTYLE, ex);

    SetLayeredWindowAttributes(g_hWnd, 0, 255, LWA_ALPHA);

    ShowWindow(g_hWnd, SW_SHOW);
    UpdateWindow(g_hWnd);
    return true;
}

// --------------------------------------------------
// DX11 init
// --------------------------------------------------
bool InitD3D() {
    RECT rc;
    GetClientRect(GetDesktopWindow(), &rc);
    int width  = rc.right - rc.left;
    int height = rc.bottom - rc.top;

    DXGI_SWAP_CHAIN_DESC sd = {};
    sd.BufferCount       = 2;
    sd.BufferDesc.Width  = width;
    sd.BufferDesc.Height = height;
    sd.BufferDesc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    sd.BufferUsage       = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    sd.OutputWindow      = g_hWnd;
    sd.SampleDesc.Count  = 1;
    sd.Windowed          = TRUE;
    sd.SwapEffect        = DXGI_SWAP_EFFECT_DISCARD;

    UINT flags = 0;
#if defined(_DEBUG)
    flags |= D3D11_CREATE_DEVICE_DEBUG;
#endif

    D3D_FEATURE_LEVEL flOut;
    HRESULT hr = D3D11CreateDeviceAndSwapChain(
        nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr,
        flags, nullptr, 0, D3D11_SDK_VERSION,
        &sd, &g_swapChain, &g_device, &flOut, &g_context
    );
    if (FAILED(hr)) return false;

    ComPtr<ID3D11Texture2D> backBuffer;
    hr = g_swapChain->GetBuffer(0, IID_PPV_ARGS(&backBuffer));
    if (FAILED(hr)) return false;

    hr = g_device->CreateRenderTargetView(backBuffer.Get(), nullptr, &g_rtv);
    if (FAILED(hr)) return false;

    g_context->OMSetRenderTargets(1, g_rtv.GetAddressOf(), nullptr);

    D3D11_VIEWPORT vp = {};
    vp.Width    = (FLOAT)width;
    vp.Height   = (FLOAT)height;
    vp.MinDepth = 0.0f;
    vp.MaxDepth = 1.0f;
    vp.TopLeftX = 0.0f;
    vp.TopLeftY = 0.0f;
    g_context->RSSetViewports(1, &vp);

    return true;
}

// --------------------------------------------------
// Desktop duplication
// --------------------------------------------------
bool InitDuplicationForMonitor(int monitorIndex) {
    g_duplication.Reset();
    g_dupTex.Reset();
    g_dupSRV.Reset();

    ComPtr<IDXGIDevice> dxgiDevice;
    HRESULT hr = g_device.As(&dxgiDevice);
    if (FAILED(hr)) return false;

    ComPtr<IDXGIAdapter> adapter;
    hr = dxgiDevice->GetAdapter(&adapter);
    if (FAILED(hr)) return false;

    ComPtr<IDXGIOutput> output;
    hr = adapter->EnumOutputs(monitorIndex, &output);
    if (FAILED(hr)) return false;

    ComPtr<IDXGIOutput1> output1;
    hr = output.As(&output1);
    if (FAILED(hr)) return false;

    hr = output1->DuplicateOutput(g_device.Get(), &g_duplication);
    if (FAILED(hr)) return false;

    DXGI_OUTDUPL_DESC dd;
    g_duplication->GetDesc(&dd);

    D3D11_TEXTURE2D_DESC td = {};
    td.Width              = dd.ModeDesc.Width;
    td.Height             = dd.ModeDesc.Height;
    td.MipLevels          = 1;
    td.ArraySize          = 1;
    td.Format             = DXGI_FORMAT_B8G8R8A8_UNORM;
    td.SampleDesc.Count   = 1;
    td.Usage              = D3D11_USAGE_DEFAULT;
    td.BindFlags          = D3D11_BIND_SHADER_RESOURCE;
    td.CPUAccessFlags     = 0;

    hr = g_device->CreateTexture2D(&td, nullptr, &g_dupTex);
    if (FAILED(hr)) return false;

    D3D11_SHADER_RESOURCE_VIEW_DESC sd = {};
    sd.Format                    = td.Format;
    sd.ViewDimension             = D3D11_SRV_DIMENSION_TEXTURE2D;
    sd.Texture2D.MipLevels       = 1;
    sd.Texture2D.MostDetailedMip = 0;
    hr = g_device->CreateShaderResourceView(g_dupTex.Get(), &sd, &g_dupSRV);
    if (FAILED(hr)) return false;

    return true;
}

// --------------------------------------------------
// Shaders (VS + PS with effects)
// --------------------------------------------------
static const char* g_VS_HLSL = R"(
struct VSIn {
    float3 pos : POSITION;
    float2 uv  : TEXCOORD0;
};
struct VSOut {
    float4 pos : SV_POSITION;
    float2 uv  : TEXCOORD0;
};
VSOut main(VSIn i) {
    VSOut o;
    o.pos = float4(i.pos, 1.0);
    o.uv  = i.uv;
    return o;
}
)";

static const char* g_PS_HLSL = R"(
Texture2D tex0 : register(t0);
SamplerState samLinear : register(s0);

cbuffer CBParams : register(b0)
{
    float Brightness;
    float Gamma;
    float EffectType; // 0=normal,1=night,2=thermal,3=HDRish
    float PerfType;   // 0=standard,1=ultra
};

float3 apply_effect(float3 c)
{
    // Performance: if Ultra, skip some heavier math
    bool ultra = (PerfType >= 0.5);

    // Optional gamma
    if (!ultra || abs(Gamma - 1.0) > 0.01)
    {
        c = pow(c, Gamma);
    }

    if (EffectType < 0.5)
    {
        // Normal
        c *= Brightness;
        return c;
    }
    else if (EffectType < 1.5)
    {
        // Night vision: grayscale → boosted green
        float gray = dot(c, float3(0.299, 0.587, 0.114));
        float g = saturate(gray * Brightness * 1.5);
        return float3(0.0, g, 0.0);
    }
    else if (EffectType < 2.5)
    {
        // Thermal: cheap pseudo color mapping
        float gray = dot(c, float3(0.299, 0.587, 0.114)) * Brightness;
        gray = saturate(gray);
        float r = saturate((gray - 0.3) * 3.0);
        float g = saturate((gray - 0.6) * 3.5);
        float b = saturate(1.0 - gray * 2.0);
        return float3(r, g, b);
    }
    else
    {
        // HDR-ish: bright but compressed (tone map)
        c *= Brightness * 2.0;
        c = c / (1.0 + c);
        return c;
    }
}

float4 main(float4 pos : SV_POSITION, float2 uv : TEXCOORD0) : SV_Target
{
    float4 c = tex0.Sample(samLinear, uv);
    float3 outc = apply_effect(c.rgb);
    return float4(saturate(outc), 1.0);
}
)";

bool InitShaders() {
    HRESULT hr;
    ComPtr<ID3DBlob> vsBlob, psBlob, errBlob;

    hr = D3DCompile(g_VS_HLSL, strlen(g_VS_HLSL), nullptr, nullptr, nullptr,
                    "main", "vs_5_0", 0, 0, &vsBlob, &errBlob);
    if (FAILED(hr)) {
        if (errBlob) OutputDebugStringA((char*)errBlob->GetBufferPointer());
        return false;
    }
    hr = D3DCompile(g_PS_HLSL, strlen(g_PS_HLSL), nullptr, nullptr, nullptr,
                    "main", "ps_5_0", 0, 0, &psBlob, &errBlob);
    if (FAILED(hr)) {
        if (errBlob) OutputDebugStringA((char*)errBlob->GetBufferPointer());
        return false;
    }

    hr = g_device->CreateVertexShader(vsBlob->GetBufferPointer(),
                                      vsBlob->GetBufferSize(),
                                      nullptr, &g_vs);
    if (FAILED(hr)) return false;

    hr = g_device->CreatePixelShader(psBlob->GetBufferPointer(),
                                     psBlob->GetBufferSize(),
                                     nullptr, &g_ps);
    if (FAILED(hr)) return false;

    D3D11_INPUT_ELEMENT_DESC il[] = {
        { "POSITION", 0, DXGI_FORMAT_R32G32B32_FLOAT, 0, 0,  D3D11_INPUT_PER_VERTEX_DATA, 0 },
        { "TEXCOORD", 0, DXGI_FORMAT_R32G32_FLOAT,    0, 12, D3D11_INPUT_PER_VERTEX_DATA, 0 },
    };

    hr = g_device->CreateInputLayout(il, 2,
                                     vsBlob->GetBufferPointer(),
                                     vsBlob->GetBufferSize(),
                                     &g_layout);
    if (FAILED(hr)) return false;

    // Constant buffer
    D3D11_BUFFER_DESC cbd = {};
    cbd.BindFlags      = D3D11_BIND_CONSTANT_BUFFER;
    cbd.ByteWidth      = sizeof(CBParams);
    cbd.Usage          = D3D11_USAGE_DEFAULT;
    hr = g_device->CreateBuffer(&cbd, nullptr, &g_cb);
    if (FAILED(hr)) return false;

    // Fullscreen quad
    FSVertex verts[4] = {
        { { -1.f, -1.f, 0.f }, { 0.f, 1.f } },
        { { -1.f,  1.f, 0.f }, { 0.f, 0.f } },
        { {  1.f, -1.f, 0.f }, { 1.f, 1.f } },
        { {  1.f,  1.f, 0.f }, { 1.f, 0.f } },
    };
    D3D11_BUFFER_DESC vbd = {};
    vbd.BindFlags   = D3D11_BIND_VERTEX_BUFFER;
    vbd.ByteWidth   = sizeof(verts);
    vbd.Usage       = D3D11_USAGE_DEFAULT;
    D3D11_SUBRESOURCE_DATA vd = {};
    vd.pSysMem = verts;
    hr = g_device->CreateBuffer(&vbd, &vd, &g_vb);
    if (FAILED(hr)) return false;

    // Sampler
    D3D11_SAMPLER_DESC sd = {};
    sd.Filter   = D3D11_FILTER_MIN_MAG_MIP_LINEAR;
    sd.AddressU = sd.AddressV = sd.AddressW = D3D11_TEXTURE_ADDRESS_CLAMP;
    sd.MinLOD   = 0;
    sd.MaxLOD   = D3D11_FLOAT32_MAX;
    hr = g_device->CreateSamplerState(&sd, &g_sampler);
    if (FAILED(hr)) return false;

    return true;
}

// --------------------------------------------------
// Gamma ramp helpers
// --------------------------------------------------
void CaptureDefaultGamma() {
    HDC hdc = GetDC(nullptr);
    if (!hdc) return;

    GammaRamp ramp = {};
    if (GetDeviceGammaRamp(hdc, &ramp)) {
        g_defaultGamma = ramp;
        g_haveDefaultGamma = true;
    }
    ReleaseDC(nullptr, hdc);
}

void ApplySystemGamma(float brightness, float gamma) {
    HDC hdc = GetDC(nullptr);
    if (!hdc) return;

    GammaRamp ramp = {};
    for (int i = 0; i < 256; ++i) {
        float v = i / 255.0f;
        v = powf(v, gamma) * brightness;
        if (v < 0.0f) v = 0.0f;
        if (v > 1.0f) v = 1.0f;
        WORD w = (WORD)(v * 65535.0f);
        ramp.Red[i] = ramp.Green[i] = ramp.Blue[i] = w;
    }
    SetDeviceGammaRamp(hdc, &ramp);
    ReleaseDC(nullptr, hdc);
}

void RestoreSystemGamma() {
    if (!g_haveDefaultGamma) return;
    HDC hdc = GetDC(nullptr);
    if (!hdc) return;
    SetDeviceGammaRamp(hdc, &g_defaultGamma);
    ReleaseDC(nullptr, hdc);
}

// --------------------------------------------------
// DXVA2 brightness helpers
// --------------------------------------------------
void EnumMonitors() {
    g_monitors.clear();

    ComPtr<IDXGIDevice> dxgiDevice;
    if (FAILED(g_device.As(&dxgiDevice))) return;

    ComPtr<IDXGIAdapter> adapter;
    if (FAILED(dxgiDevice->GetAdapter(&adapter))) return;

    UINT i = 0;
    while (true) {
        ComPtr<IDXGIOutput> output;
        if (adapter->EnumOutputs(i, &output) == DXGI_ERROR_NOT_FOUND)
            break;

        DXGI_OUTPUT_DESC od = {};
        output->GetDesc(&od);

        MonitorInfo mi;
        mi.index      = (int)i;
        mi.deviceName = od.DeviceName;
        mi.hMonitor   = od.Monitor;

        // Try DXVA2 brightness
        DWORD numPhys = 0;
        if (GetNumberOfPhysicalMonitorsFromHMONITOR(mi.hMonitor, &numPhys)) {
            std::vector<PHYSICAL_MONITOR> phys(numPhys);
            if (GetPhysicalMonitorsFromHMONITOR(mi.hMonitor, numPhys, phys.data())) {
                if (numPhys > 0) {
                    DWORD cur, minB, maxB;
                    if (GetMonitorBrightness(phys[0].hPhysicalMonitor, &minB, &cur, &maxB)) {
                        mi.hasBrightness  = true;
                        mi.minBright      = minB;
                        mi.maxBright      = maxB;
                        mi.defaultBright  = cur;
                    }
                }
                DestroyPhysicalMonitors(numPhys, phys.data());
            }
        }

        g_monitors.push_back(mi);
        ++i;
    }

    if (g_monitors.empty()) {
        MonitorInfo dummy;
        dummy.index = 0;
        dummy.deviceName = L"PrimaryMonitor";
        dummy.hMonitor = nullptr;
        g_monitors.push_back(dummy);
    }
}

void RestoreMonitorBrightness(int monitorIndex) {
    if (monitorIndex < 0 || monitorIndex >= (int)g_monitors.size()) return;
    MonitorInfo &mi = g_monitors[monitorIndex];
    if (!mi.hasBrightness) return;

    DWORD numPhys = 0;
    if (!GetNumberOfPhysicalMonitorsFromHMONITOR(mi.hMonitor, &numPhys)) return;
    std::vector<PHYSICAL_MONITOR> phys(numPhys);
    if (!GetPhysicalMonitorsFromHMONITOR(mi.hMonitor, numPhys, phys.data())) return;

    if (numPhys > 0) {
        SetMonitorBrightness(phys[0].hPhysicalMonitor, mi.defaultBright);
    }
    DestroyPhysicalMonitors(numPhys, phys.data());
}

// --------------------------------------------------
// HDR status check (best-effort via registry)
// --------------------------------------------------
bool? CheckHDRStatus() {
    HKEY hKey;
    // One common location; there are others, but this is "good enough"
    if (RegOpenKeyExA(HKEY_CURRENT_USER,
                      "Software\\Microsoft\\Windows\\CurrentVersion\\VideoSettings",
                      0, KEY_READ, &hKey) != ERROR_SUCCESS)
        return std::nullopt;

    DWORD val = 0;
    DWORD len = sizeof(val);
    if (RegQueryValueExA(hKey, "HdrEnable", nullptr, nullptr, (LPBYTE)&val, &len) == ERROR_SUCCESS) {
        RegCloseKey(hKey);
        return (val != 0);
    }
    RegCloseKey(hKey);
    return std::nullopt;
}

// --------------------------------------------------
// Profiles (simple text file, not strict JSON to keep it compact)
// Format per line:
// key brightness gamma opacity mode effect perf monitorIndex
// --------------------------------------------------
std::string ProfilesPath() {
    char buf[MAX_PATH];
    GetModuleFileNameA(nullptr, buf, MAX_PATH);
    std::string path(buf);
    size_t pos = path.find_last_of("\\/");
    if (pos != std::string::npos) path = path.substr(0, pos + 1);
    path += "fullbright_profiles.txt";
    return path;
}

void LoadProfiles() {
    std::lock_guard<std::mutex> lock(g_profileMutex);
    g_profiles.clear();
    std::ifstream f(ProfilesPath());
    if (!f) {
        // default global
        Profile p;
        p.brightness   = g_settings.brightness;
        p.gamma        = g_settings.gamma;
        p.opacity      = g_settings.opacity;
        p.mode         = g_settings.mode;
        p.effect       = g_settings.effect;
        p.perf         = g_settings.perf;
        p.monitorIndex = g_currentMonitorIndex;
        g_profiles["global"] = p;
        return;
    }
    std::string line;
    while (std::getline(f, line)) {
        if (line.empty()) continue;
        std::istringstream ss(line);
        std::string key;
        Profile p;
        int mode, eff, perf;
        ss >> key >> p.brightness >> p.gamma >> p.opacity >> mode >> eff >> perf >> p.monitorIndex;
        p.mode   = (Mode)mode;
        p.effect = (Effect)eff;
        p.perf   = (PerfMode)perf;
        g_profiles[key] = p;
    }
    if (g_profiles.find("global") == g_profiles.end()) {
        Profile p;
        p.brightness   = g_settings.brightness;
        p.gamma        = g_settings.gamma;
        p.opacity      = g_settings.opacity;
        p.mode         = g_settings.mode;
        p.effect       = g_settings.effect;
        p.perf         = g_settings.perf;
        p.monitorIndex = g_currentMonitorIndex;
        g_profiles["global"] = p;
    }
}

void SaveProfiles() {
    std::lock_guard<std::mutex> lock(g_profileMutex);
    std::ofstream f(ProfilesPath());
    if (!f) return;
    for (auto &kv : g_profiles) {
        const std::string &key = kv.first;
        const Profile &p = kv.second;
        f << key << " " << p.brightness << " " << p.gamma << " " << p.opacity
          << " " << (int)p.mode << " " << (int)p.effect << " " << (int)p.perf
          << " " << p.monitorIndex << "\n";
    }
}

void ApplyProfile(const Profile &p) {
    g_settings.brightness = p.brightness;
    g_settings.gamma      = p.gamma;
    g_settings.opacity    = p.opacity;
    g_settings.mode       = p.mode;
    g_settings.effect     = p.effect;
    g_settings.perf       = p.perf;
    g_currentMonitorIndex = p.monitorIndex;
    InitDuplicationForMonitor(g_currentMonitorIndex);
}

void SaveCurrentToProfile(const std::string &key) {
    std::lock_guard<std::mutex> lock(g_profileMutex);
    Profile p;
    p.brightness   = g_settings.brightness;
    p.gamma        = g_settings.gamma;
    p.opacity      = g_settings.opacity;
    p.mode         = g_settings.mode;
    p.effect       = g_settings.effect;
    p.perf         = g_settings.perf;
    p.monitorIndex = g_currentMonitorIndex;
    g_profiles[key] = p;
    SaveProfiles();
}

// --------------------------------------------------
// Active game detection (foreground exe name)
// --------------------------------------------------
std::string GetActiveExeName() {
    HWND hwnd = GetForegroundWindow();
    if (!hwnd) return {};
    DWORD pid = 0;
    GetWindowThreadProcessId(hwnd, &pid);
    if (!pid) return {};
    HANDLE hProc = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ, FALSE, pid);
    if (!hProc) return {};
    char path[MAX_PATH];
    DWORD size = MAX_PATH;
    if (GetProcessImageFileNameA(hProc, path, size) == 0) {
        CloseHandle(hProc);
        return {};
    }
    CloseHandle(hProc);
    // extract exe name
    std::string full(path);
    size_t pos = full.find_last_of("\\/");
    if (pos != std::string::npos) full = full.substr(pos + 1);
    return full;
}

void ProfileWatcherLoop() {
    while (g_running) {
        std::string exe = GetActiveExeName();
        if (!exe.empty() && exe != g_currentExeName) {
            g_currentExeName = exe;
            std::string key = "game:" + exe;

            std::lock_guard<std::mutex> lock(g_profileMutex);
            auto it = g_profiles.find(key);
            if (it != g_profiles.end()) {
                g_currentProfileKey = key;
                ApplyProfile(it->second);
            } else {
                g_currentProfileKey = "global";
                ApplyProfile(g_profiles["global"]);
            }
        }
        Sleep(1000);
    }
}

// --------------------------------------------------
// Frame rendering
// --------------------------------------------------
void RenderOverlayFrame() {
    // Acquire dup frame
    if (!g_duplication) return;

    ComPtr<IDXGIResource> res;
    DXGI_OUTDUPL_FRAME_INFO fi = {};
    HRESULT hr = g_duplication->AcquireNextFrame(0, &fi, &res);
    if (hr == DXGI_ERROR_WAIT_TIMEOUT) {
        // no new frame
    } else if (SUCCEEDED(hr)) {
        ComPtr<ID3D11Texture2D> tex;
        if (SUCCEEDED(res.As(&tex))) {
            g_context->CopyResource(g_dupTex.Get(), tex.Get());
        }
        g_duplication->ReleaseFrame();
    }

    float clear[4] = {0, 0, 0, 1};
    g_context->ClearRenderTargetView(g_rtv.Get(), clear);

    if (g_settings.mode == Mode::Overlay) {
        // Update constant buffer
        CBParams cb = {};
        cb.Brightness = g_settings.brightness;
        cb.Gamma      = g_settings.gamma;
        cb.EffectType = (float)g_settings.effect;
        cb.PerfType   = (float)g_settings.perf;
        g_context->UpdateSubresource(g_cb.Get(), 0, nullptr, &cb, 0, 0);

        UINT stride = sizeof(FSVertex);
        UINT offset = 0;
        g_context->IASetVertexBuffers(0, 1, g_vb.GetAddressOf(), &stride, &offset);
        g_context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLESTRIP);
        g_context->IASetInputLayout(g_layout.Get());

        g_context->VSSetShader(g_vs.Get(), nullptr, 0);
        g_context->PSSetShader(g_ps.Get(), nullptr, 0);
        g_context->PSSetShaderResources(0, 1, g_dupSRV.GetAddressOf());
        g_context->PSSetSamplers(0, 1, g_sampler.GetAddressOf());
        g_context->PSSetConstantBuffers(0, 1, g_cb.GetAddressOf());

        g_context->Draw(4, 0);
    }

    // ImGui render
    ImGui_ImplDX11_RenderDrawData(ImGui::GetDrawData());

    g_swapChain->Present(0, 0);
}

// --------------------------------------------------
// ImGui UI
// --------------------------------------------------
void BuildUI() {
    ImGui::Begin("FullBright Control", nullptr, ImGuiWindowFlags_AlwaysAutoResize);

    // Monitor selection & info
    if (!g_monitors.empty()) {
        std::vector<std::string> labels;
        labels.reserve(g_monitors.size());
        for (auto &mi : g_monitors) {
            std::wstring ws = mi.deviceName;
            std::string  s(ws.begin(), ws.end());
            labels.push_back(std::to_string(mi.index) + " - " + s);
        }
        std::vector<const char*> cstrs;
        for (auto &s : labels) cstrs.push_back(s.c_str());

        int idx = g_currentMonitorIndex;
        if (ImGui::Combo("Monitor", &idx, cstrs.data(), (int)cstrs.size())) {
            g_currentMonitorIndex = idx;
            InitDuplicationForMonitor(g_currentMonitorIndex);
        }

        if (g_currentMonitorIndex >= 0 && g_currentMonitorIndex < (int)g_monitors.size()) {
            auto &mi = g_monitors[g_currentMonitorIndex];
            std::wstring ws = mi.deviceName;
            std::string  s(ws.begin(), ws.end());
            ImGui::Text("Tweaking monitor: %s", s.c_str());
            if (mi.hasBrightness) {
                ImGui::Text("Default HW brightness: %lu (min %lu, max %lu)",
                            mi.defaultBright, mi.minBright, mi.maxBright);
            } else {
                ImGui::Text("Hardware brightness control: unavailable");
            }
        }
    }

    // HDR status
    {
        auto hdr = CheckHDRStatus();
        if (hdr.has_value()) {
            if (*hdr) {
                ImGui::TextColored(ImVec4(1,0.3f,0.3f,1), "HDR: ON (effects may be limited)");
            } else {
                ImGui::TextColored(ImVec4(0.3f,1,0.3f,1), "HDR: OFF (optimal)");
            }
        } else {
            ImGui::TextColored(ImVec4(1,1,0.3f,1), "HDR: Unknown");
        }
    }

    // Mode
    {
        int mode = (g_settings.mode == Mode::Overlay) ? 0 : 1;
        if (ImGui::RadioButton("Overlay mode", mode == 0)) {
            mode = 0;
            g_settings.mode = Mode::Overlay;
            RestoreSystemGamma();
        }
        ImGui::SameLine();
        if (ImGui::RadioButton("System gamma mode", mode == 1)) {
            mode = 1;
            g_settings.mode = Mode::SystemGamma;
            ApplySystemGamma(g_settings.brightness, g_settings.gamma);
        }
    }

    ImGui::Separator();

    ImGui::SliderFloat("Brightness", &g_settings.brightness, 0.1f, 3.0f, "%.2f");
    ImGui::SliderFloat("Gamma",      &g_settings.gamma,      0.2f, 2.5f, "%.2f");

    const char* effects[] = { "Normal", "Night Vision", "Thermal", "HDR-ish" };
    int eff = (int)g_settings.effect;
    if (ImGui::Combo("Effect", &eff, effects, IM_ARRAYSIZE(effects))) {
        g_settings.effect = (Effect)eff;
    }

    const char* perfModes[] = { "Standard", "Ultra" };
    int pm = (int)g_settings.perf;
    if (ImGui::Combo("Perf mode", &pm, perfModes, IM_ARRAYSIZE(perfModes))) {
        g_settings.perf = (PerfMode)pm;
    }

    ImGui::Separator();

    // Profiles
    ImGui::Text("Current profile: %s", g_currentProfileKey.c_str());
    ImGui::Text("Active EXE: %s", g_currentExeName.empty() ? "(none)" : g_currentExeName.c_str());

    if (ImGui::Button("Save Global Profile")) {
        SaveCurrentToProfile("global");
        g_currentProfileKey = "global";
    }
    if (ImGui::Button("Save Current Game Profile")) {
        if (!g_currentExeName.empty()) {
            std::string key = "game:" + g_currentExeName;
            SaveCurrentToProfile(key);
            g_currentProfileKey = key;
        }
    }

    if (ImGui::Button("Restore Monitor Defaults")) {
        RestoreSystemGamma();
        RestoreMonitorBrightness(g_currentMonitorIndex);
    }

    ImGui::End();
}

// --------------------------------------------------
// Main
// --------------------------------------------------
int APIENTRY WinMain(HINSTANCE hInst, HINSTANCE, LPSTR, int) {
    if (!InitWindow(hInst)) return -1;
    if (!InitD3D()) return -1;

    CaptureDefaultGamma();
    EnumMonitors();
    LoadProfiles();

    // Start with global profile
    {
        std::lock_guard<std::mutex> lock(g_profileMutex);
        ApplyProfile(g_profiles["global"]);
    }
    InitDuplicationForMonitor(g_currentMonitorIndex);
    InitShaders();

    // ImGui init
    IMGUI_CHECKVERSION();
    ImGui::CreateContext();
    ImGui::StyleColorsDark();
    ImGui_ImplWin32_Init(g_hWnd);
    ImGui_ImplDX11_Init(g_device.Get(), g_context.Get());

    // Profile watcher thread
    HANDLE hThread = CreateThread(nullptr, 0, [](LPVOID) -> DWORD {
        ProfileWatcherLoop();
        return 0;
    }, nullptr, 0, nullptr);

    MSG msg = {};
    while (g_running) {
        while (PeekMessage(&msg, nullptr, 0, 0, PM_REMOVE)) {
            if (msg.message == WM_QUIT) g_running = false;
            TranslateMessage(&msg);
            DispatchMessage(&msg);
        }
        if (!g_running) break;

        // Begin ImGui frame
        ImGui_ImplDX11_NewFrame();
        ImGui_ImplWin32_NewFrame();
        ImGui::NewFrame();

        BuildUI();
        ImGui::Render();

        RenderOverlayFrame();
    }

    g_running = false;
    WaitForSingleObject(hThread, 2000);

    // Cleanup
    RestoreSystemGamma();
    RestoreMonitorBrightness(g_currentMonitorIndex);

    ImGui_ImplDX11_Shutdown();
    ImGui_ImplWin32_Shutdown();
    ImGui::DestroyContext();

    g_rtv.Reset();
    g_swapChain.Reset();
    g_context.Reset();
    g_device.Reset();
    g_duplication.Reset();

    return 0;
}