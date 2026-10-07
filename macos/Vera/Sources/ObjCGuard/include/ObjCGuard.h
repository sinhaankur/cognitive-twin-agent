#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// Run `block` inside an Objective-C @try/@catch. If it throws an NSException
/// (which Swift cannot catch and which otherwise aborts the process with
/// SIGABRT — e.g. the Photos framework's PHQuery predicate failures), this
/// returns a non-nil NSError describing it instead of crashing. Returns nil on
/// success. This is the one safe bridge for calling exception-throwing ObjC APIs
/// (Photos fetches) from Swift without taking down the whole app.
NSError * _Nullable VeraCatchingExceptions(void (^ _Nonnull block)(void));

NS_ASSUME_NONNULL_END
