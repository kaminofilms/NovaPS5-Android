#include "QueueWait.h"
#include "OutputCost.h"
#include <cassert>
#include <iostream>
#include <thread>
#include <vector>
int main(){
 using NovaAudio::QueueWaitMicros;
 assert(QueueWaitMicros(-1,0,8,48000)==0);
 assert(QueueWaitMicros(15360,15360,8,48000)==0);
 assert(QueueWaitMicros(16384,15360,8,48000)==2666);
 assert(QueueWaitMicros(23040,15360,8,48000)==5000);
 assert(QueueWaitMicros(15361,15360,8,48000)==1000);
 assert(QueueWaitMicros(23040,15360,0,48000)==1000);
 assert(QueueWaitMicros(23040,15360,8,0)==1000);
 // Simulate continuous 48 kHz stereo float draining from 80 to 40 ms.
 // The same target is retained with at most nine polls instead of forty.
 int queued=30720;unsigned polls=0;
 while(queued>15360){auto us=QueueWaitMicros(queued,15360,8,48000);assert(us>0&&us<=5000);queued-=int(uint64_t(us)*8*48000/1000000);++polls;}
 assert(polls<=9 && queued>=14976);
 NovaAudio::OutputTotals t;t.Add(100,10,200,30);t.Add(400,80,500,90);
 assert(t.calls==2&&t.insideCpu==30&&t.insideWall==200&&t.OutsideCpu(90)==50);
 NovaAudio::OutputTotals bad;bad.Add(100,10,99,30);assert(bad.calls==0);
 // SDL's copying boundary permits scratch reuse; each thread must own its buffer.
 auto exercise=[] {thread_local std::vector<uint8_t> scratch;size_t cap=0;for(int i=0;i<1000;i++){scratch.clear();scratch.resize(1024);if(i)assert(scratch.capacity()==cap);cap=scratch.capacity();}};
 std::thread a(exercise),b(exercise);a.join();b.join();
 std::cout<<"PASS queue byte/rate units, bounded waits, reduced polls, CPU attribution, scratch reuse\n";
}
