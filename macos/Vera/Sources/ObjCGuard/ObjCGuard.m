#import "ObjCGuard.h"

NSError * _Nullable VeraCatchingExceptions(void (^ _Nonnull block)(void)) {
    @try {
        block();
        return nil;
    }
    @catch (NSException *e) {
        NSMutableDictionary *info = [NSMutableDictionary dictionary];
        if (e.reason) info[NSLocalizedDescriptionKey] = e.reason;
        if (e.name)   info[@"ExceptionName"] = e.name;
        return [NSError errorWithDomain:@"VeraObjCGuard" code:1 userInfo:info];
    }
}
