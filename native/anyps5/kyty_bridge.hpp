#pragma once
namespace Loader { class SymbolDatabase; }
namespace NovaAnyPS5 {
bool Enabled();
void Initialize();
void RunWindow();
void Shutdown();
void RegisterGraphicsExports(Loader::SymbolDatabase* symbols);
void RegisterVideoExports(Loader::SymbolDatabase* symbols);
}
