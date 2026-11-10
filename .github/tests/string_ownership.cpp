#include "4DPlugin-JSON.h"
#include "ARRAY_TEXT.h"
#include "C_TEXT.h"
#include "PrivateTypes.h"
#include "EntryPoints.h"

#include <cassert>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>
#include <set>
#include <string>

namespace {
using Text = std::basic_string<PA_Unichar>;
struct Reference {
    int count = 1;
    std::map<Text, PA_Variable> properties;
};
std::map<PA_Unichar*, size_t> strings;
std::map<PA_Handle, size_t> handles;
std::set<Reference*> references;
bool nullEmpty = false;

Text text(const PA_Unistring& value) {
    PA_Unichar* pointer = value.fString;
    if (!pointer) {
        assert(value.fLength == 0);
        return {};
    }
    assert(strings.count(pointer));
    assert(strings.at(pointer) == static_cast<size_t>(value.fLength));
    assert(pointer[value.fLength] == 0);
    return Text(pointer, value.fLength);
}

PA_Unistring makeString(const Text& value) {
    PA_Unistring result = {};
    result.fLength = static_cast<PA_long32>(value.size());
    if (!value.empty() || !nullEmpty) {
        result.fString = new PA_Unichar[value.size() + 1];
        std::copy(value.begin(), value.end(), result.fString);
        result.fString[value.size()] = 0;
        PA_Unichar* pointer = result.fString;
        assert(strings.emplace(pointer, value.size()).second);
    }
    return result;
}

void freeString(PA_Unistring value) {
    text(value);
    PA_Unichar* pointer = value.fString;
    if (pointer) {
        assert(strings.erase(pointer) == 1);
        delete[] pointer;
    }
}

Reference* makeReference() {
    Reference* result = new Reference;
    assert(references.insert(result).second);
    return result;
}

void retain(Reference* value) {
    if (value) {
        assert(references.count(value));
        ++value->count;
    }
}

void clear(PA_Variable& value);

void release(Reference* value) {
    if (!value) return;
    assert(references.count(value));
    if (--value->count == 0) {
        for (auto& property : value->properties) clear(property.second);
        references.erase(value);
        delete value;
    }
}

PA_Variable copy(PA_Variable value) {
    switch (value.fType) {
        case eVK_Unistring:
            value.uValue.fString = makeString(text(value.uValue.fString));
            break;
        case eVK_Object:
            retain(static_cast<Reference*>(value.uValue.fObject));
            break;
        case eVK_Collection:
            retain(static_cast<Reference*>(value.uValue.fCollection));
            break;
        case eVK_Picture:
            retain(static_cast<Reference*>(value.uValue.fPicture));
            break;
        case eVK_Boolean:
        case eVK_Real:
        case eVK_Longint:
        case eVK_Undefined:
            break;
        default:
            assert(false && "unexpected variable copy");
    }
    return value;
}

void clear(PA_Variable& value) {
    switch (value.fType) {
        case eVK_Unistring:
            freeString(value.uValue.fString);
            break;
        case eVK_ArrayUnicode: {
            PA_Handle handle = value.uValue.fArray.fData;
            if (handle) {
                assert(handles.count(handle));
                assert(handles.at(handle) ==
                       (value.uValue.fArray.fNbElements + 1) * sizeof(PA_Unistring));
                auto elements = reinterpret_cast<PA_Unistring*>(*handle);
                for (int i = 0; i <= value.uValue.fArray.fNbElements; ++i)
                    freeString(elements[i]);
                handles.erase(handle);
                std::free(*handle);
                std::free(handle);
            }
            break;
        }
        case eVK_Object:
            release(static_cast<Reference*>(value.uValue.fObject));
            break;
        case eVK_Collection:
            release(static_cast<Reference*>(value.uValue.fCollection));
            break;
        case eVK_Picture:
            release(static_cast<Reference*>(value.uValue.fPicture));
            break;
        case eVK_Boolean:
        case eVK_Real:
        case eVK_Longint:
        case eVK_Undefined:
            break;
        default:
            assert(false && "unexpected variable cleanup");
    }
    value = {};
    value.fType = eVK_Undefined;
}

PA_Variable& property(EngineBlock* eb) {
    auto object = static_cast<Reference*>(eb->fPtr1);
    assert(references.count(object));
    PA_Variable empty = {};
    empty.fType = eVK_Undefined;
    return object->properties.emplace(text(eb->fUniString1), empty).first->second;
}

void engine(short selector, EngineBlock* eb) {
    eb->fError = eER_NoErr;
    switch (selector) {
        case EX_CREATE_UNISTRING:
            eb->fUniString1 = makeString(Text(reinterpret_cast<PA_Unichar*>(eb->fHandle)));
            break;
        case EX_DISPOSE_UNISTRING:
            freeString(eb->fUniString1);
            break;
        case EX_SET_UNISTRING: {
            Text input(reinterpret_cast<PA_Unichar*>(eb->fHandle));
            freeString(eb->fUniString1);
            eb->fUniString1 = makeString(input);
            break;
        }
        case EX_VARIABLE_TO_STRING: {
            auto value = reinterpret_cast<PA_Variable*>(eb->fHandle);
            assert(value->fType == eVK_Unistring);
            text(value->uValue.fString);
            eb->fUniString1 = value->uValue.fString;
            break;
        }
        case EX_CLEAR_VARIABLE:
            clear(*static_cast<PA_Variable*>(eb->fPtr1));
            break;
        case EX_SET_OBJ_VALUE: {
            assert(eb->fShort == eVK_Object);
            PA_Variable replacement = copy(*static_cast<PA_Variable*>(eb->fPtr2));
            clear(property(eb));
            property(eb) = replacement;
            break;
        }
        case EX_GET_OBJ_VALUE:
            assert(eb->fShort == eVK_Object);
            *static_cast<PA_Variable*>(eb->fPtr2) = copy(property(eb));
            break;
        case EX_CREATE_PICTURE:
            eb->fPicture = makeReference();
            break;
        case EX_DISPOSE_PICTURE:
            release(static_cast<Reference*>(eb->fPicture));
            break;
        case EX_HANDLE_MANAGER: {
            PA_Handle handle = eb->fHandle;
            switch (eb->fParam1) {
                case 1:
                    handle = static_cast<PA_Handle>(std::malloc(sizeof(*handle)));
                    assert(handle);
                    *handle = static_cast<char*>(std::malloc(eb->fParam2));
                    assert(*handle);
                    handles[handle] = eb->fParam2;
                    eb->fHandle = handle;
                    break;
                case 2:
                    assert(handles.erase(handle) == 1);
                    std::free(*handle);
                    std::free(handle);
                    break;
                case 3: {
                    assert(handles.count(handle));
                    auto data = static_cast<char*>(std::realloc(*handle, eb->fParam2));
                    assert(data);
                    *handle = data;
                    handles[handle] = eb->fParam2;
                    break;
                }
                case 4:
                    eb->fParam2 = handles.at(handle);
                    break;
                case 5:
                    assert(handles.count(handle));
                    eb->fParam3 = reinterpret_cast<sLONG_PTR>(*handle);
                    break;
                case 6:
                    assert(handles.count(handle));
                    break;
                default:
                    assert(false && "unexpected handle operation");
            }
            break;
        }
        case EX_EXECUTE_COMMAND_BY_ID: {
            // PA_ExecuteCommandByID forwards ID/params/result in these fields.
            auto params = static_cast<PA_Variable**>(eb->fPtr1);
            auto result = static_cast<PA_Variable*>(eb->fPtr2);
            *result = {};
            if (eb->fParam1 == 1231) {
                assert(eb->fParam2 == 2);
                auto object = static_cast<Reference*>(params[0]->uValue.fObject);
                assert(references.count(object));
                PA_SetBooleanVariable(result,
                    object->properties.count(text(params[1]->uValue.fString)) != 0);
            } else if (eb->fParam1 == 1225) {
                assert(eb->fParam2 == 1);
                auto original = static_cast<Reference*>(params[0]->uValue.fObject);
                auto duplicate = makeReference();
                for (const auto& entry : original->properties)
                    duplicate->properties.emplace(entry.first, copy(entry.second));
                PA_SetObjectVariable(result, duplicate);
            } else if (eb->fParam1 == 1217) {
                assert(eb->fParam2 == 1);
                auto object = static_cast<Reference*>(params[0]->uValue.fObject);
                const PA_Variable& value = object->properties.at(Text{'j'});
                *result = copy(value);
            } else {
                assert(false && "unexpected command");
            }
            break;
        }
        default:
            std::cerr << "Unexpected engine selector " << selector << '\n';
            std::abort();
    }
}

void balanced(const char* label) {
    if (!strings.empty() || !references.empty() || !handles.empty()) {
        std::cerr << label << ": leaked strings=" << strings.size()
                  << " references=" << references.size()
                  << " handles=" << handles.size() << '\n';
        std::abort();
    }
}

void churn() {
    for (int i = 0; i < 32; ++i) {
        auto value = makeString(Text(64 + i, 'x'));
        freeString(value);
    }
}

void setters(int kind) {
    const char* values[] = {"ASCII", "\xE6\x97\xA5\xE6\x9C\xAC", "\xF0\x9F\x98\x80", ""};
    const wchar_t* wide[] = {L"ASCII", L"\u65E5\u672C", L"\U0001F600", L""};
    const Text expected[] = {{'A','S','C','I','I'}, {0x65e5,0x672c}, {0xd83d,0xde00}, {}};
    auto object = makeReference();
    for (int repeat = 0; repeat < 3; ++repeat) {
        for (int i = 0; i < 4; ++i) {
            if (kind == 0) ob_set_s(object, "key", values[i]);
            if (kind == 1) ob_set_s(object, L"key", values[i]);
            if (kind == 2) ob_set_a(object, L"key", wide[i]);
            churn();
            assert(text(object->properties.at(Text{'k','e','y'}).uValue.fString) == expected[i]);
        }
    }
    PA_DisposeObject(object);
    balanced("string setter");
}

void pictures() {
    auto object = makeReference();
    auto picture = makeReference();
    ob_set_p(object, L"picture", picture); // Existing helper consumes the supplied owner.
    assert(references.count(picture) && picture->count == 1);
    PA_DisposeObject(object);
    balanced("picture setter");
}

void put(Reference* object, const Text& key, PA_Variable value) {
    auto old = object->properties.find(key);
    if (old != object->properties.end()) {
        clear(old->second);
        old->second = value;
    } else {
        object->properties.emplace(key, value);
    }
}

void getters() {
    const char* values[] = {"ASCII", "\xE6\x97\xA5\xE6\x9C\xAC", "\xF0\x9F\x98\x80", ""};
    const Text expected[] = {{'A','S','C','I','I'}, {0x65e5,0x672c}, {0xd83d,0xde00}, {}};
    for (int i = 0; i < 4; ++i) {
        auto object = makeReference();
        PA_Variable input = {};
        input.fType = eVK_Unistring;
        input.uValue.fString = makeString(expected[i]);
        put(object, Text{'k'}, input);
        CUTF8String output;
        assert(ob_get_a(object, L"k", &output));
        churn();
        assert(output == CUTF8String(reinterpret_cast<const uint8_t*>(values[i])));
        // Every mismatched getter must release the owning returned string.
        assert(!ob_get_b(object, L"k"));
        assert(ob_get_n(object, L"k") == 0);
        assert(ob_get_c(object, L"k") == nullptr);
        put(object, Text{'j'}, copy(input));
        ob_stringify(object, &output);
        assert(output == CUTF8String(reinterpret_cast<const uint8_t*>(values[i])));
        PA_DisposeObject(object);
        balanced("string getters and mismatches");
    }
    auto object = makeReference();
    PA_Variable input = {};
    PA_SetBooleanVariable(&input, true);
    put(object, Text{'b'}, input);
    assert(ob_get_b(object, L"b"));
    PA_SetRealVariable(&input, 42.5);
    put(object, Text{'n'}, input);
    assert(ob_get_n(object, L"n") == 42.5);
    auto collection = makeReference();
    PA_SetCollectionVariable(&input, collection);
    put(object, Text{'c'}, input);
    CUTF8String output;
    assert(ob_get_a(object, L"c", &output)); // Mismatch releases its retained reference.
    assert(collection->count == 1);
    auto returned = ob_get_c(object, L"c");
    assert(returned == collection && collection->count == 2);
    PA_DisposeObject(object);
    assert(references.count(collection) && collection->count == 1);
    PA_DisposeCollection(returned);
    balanced("collection handoff");

    object = makeReference();
    collection = makeReference();
    PA_SetCollectionVariable(&input, collection);
    put(object, Text{'j'}, input);
    output = CUTF8String(reinterpret_cast<const uint8_t*>("unchanged"));
    ob_stringify(object, &output);
    assert(output == CUTF8String(reinterpret_cast<const uint8_t*>("unchanged")));
    assert(collection->count == 1);
    PA_DisposeObject(object);
    balanced("stringify wrong-kind owning result");

    object = makeReference();
    auto child = makeReference();
    auto list = makeReference();
    ob_set_o(object, L"o", child);
    ob_set_c(object, L"c", list);
    assert(child->count == 1 && list->count == 1);
    PA_DisposeObject(object);
    balanced("object and collection setters");
}

void arrays() {
    const Text expected[] = {{'A'}, {0x65e5}, {0xd83d,0xde00}, {}};
    PA_Variable input = PA_CreateVariable(eVK_ArrayUnicode);
    PA_ResizeArray(&input, 3);
    for (int i = 0; i < 4; ++i) {
        auto value = makeString(expected[i]);
        PA_SetStringInArray(input, i, &value);
    }
    ARRAY_TEXT wrapper;
    BytePtr arguments[] = {reinterpret_cast<BytePtr>(&input)};
    wrapper.fromParamAtIndex(arguments, 1);
    PA_ClearVariable(&input);
    churn();
    assert(wrapper.getSize() == 4);
    PA_Variable output = PA_CreateVariable(eVK_Undefined);
    arguments[0] = reinterpret_cast<BytePtr>(&output);
    wrapper.toParamAtIndex(arguments, 1);
    for (int repeat = 0; repeat < 3; ++repeat) {
        churn();
        for (int i = 0; i < 4; ++i)
            assert(text(PA_GetStringInArray(output, i)) == expected[i]);
        // Each transfer must have an allocation distinct from every other element.
        auto elements = reinterpret_cast<PA_Unistring*>(*output.uValue.fArray.fData);
        assert(elements[0].fString != elements[1].fString);
        assert(elements[1].fString != elements[2].fString);
        wrapper.toParamAtIndex(arguments, 1);
    }
    wrapper.setSize(2);
    wrapper.toParamAtIndex(arguments, 1);
    assert(output.uValue.fArray.fNbElements == 1);
    assert(text(PA_GetStringInArray(output, 1)) == expected[1]);
    PA_Variable independent = PA_CreateVariable(eVK_Undefined);
    arguments[0] = reinterpret_cast<BytePtr>(&independent);
    wrapper.toParamAtIndex(arguments, 1);
    assert(PA_GetStringInArray(output, 1).fString !=
           PA_GetStringInArray(independent, 1).fString);
    PA_ClearVariable(&output);
    churn();
    assert(text(PA_GetStringInArray(independent, 1)) == expected[1]);
    wrapper.setSize(0);
    wrapper.toParamAtIndex(arguments, 1);
    assert(independent.uValue.fArray.fNbElements == 0);
    PA_ClearVariable(&independent);
    balanced("array copy transfer replacement shrink clear");

    output = PA_CreateVariable(eVK_ArrayUnicode);
    for (int index : {-1, 1}) {
        auto value = makeString(Text{'x'});
        auto pointer = value.fString;
        PA_SetStringInArray(output, index, &value);
        assert(strings.count(pointer));
        PA_DisposeUnistring(&value);
    }
    PA_SetStringInArray(output, 0, nullptr);
    PA_ClearVariable(&output);
    for (auto kind : {eVK_Longint, eVK_ArrayUnicode}) {
        output = {};
        output.fType = kind;
        auto value = makeString(Text{'x'});
        PA_SetStringInArray(output, 0, &value); // Wrong kind or null array data.
        assert(text(value) == Text{'x'});
        PA_DisposeUnistring(&value);
        PA_ClearVariable(&output);
    }
    balanced("rejected array destinations");
}

void scalarCopies() {
    const Text expected[] = {{'A'}, {0x65e5}, {0xd83d,0xde00}, {}};
    for (const auto& fixture : expected) {
        auto value = makeString(fixture);
        BytePtr arguments[] = {reinterpret_cast<BytePtr>(&value)};
        C_TEXT wrapper;
        wrapper.fromParamAtIndex(arguments, 1);
        PA_DisposeUnistring(&value);
        churn();
        assert(wrapper.getUTF16Length() == fixture.size());
        assert(Text(wrapper.getUTF16StringPtr(), wrapper.getUTF16Length()) == fixture);
        value = makeString(Text{'o','l','d'});
        wrapper.toParamAtIndex(arguments, 1);
        assert(text(value) == fixture);
        PA_DisposeUnistring(&value);
    }
    balanced("C_TEXT parameter copy");
}
}

int main(int argc, char** argv) {
    assert(argc == 3);
    nullEmpty = std::string(argv[1]) == "null";
    gCall4D = engine;
    std::string test = argv[2];
    if (test == "setters-narrow") setters(0);
    else if (test == "setters-wide") setters(1);
    else if (test == "setters-unicode") setters(2);
    else if (test == "pictures") pictures();
    else if (test == "getters") getters();
    else if (test == "arrays") arrays();
    else if (test == "scalars") scalarCopies();
    else assert(false);
    balanced("final");
    std::cout << test << " " << argv[1] << " PASS\n";
}
